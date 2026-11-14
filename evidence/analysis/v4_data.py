"""Request-level and fee-level facts for the v4 proposal, read from recorded journals only (no network, no worlds).

For every pinned run (governor_parse.RUNS, which excludes wc721c95a136b417e5d7c and runs without summary.json):
every price request with what we quoted and whether we won it, the dealer's trust count when it arrived
(RULES.md:163-165, counted from our own ledger), every deadline_close, every booking with the fee schedule
it was booked under, and the per-order outcomes of governor_parse (late, done, P&L).
"""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path

from desk.journal import load
from desk.policy import risk

from evidence.analysis import governor_parse as gp

ROOT = gp.ROOT
DAY = 1440
TRUST_CAP = 25


@dataclass
class Req:
    id: str
    dealer: str
    arrived: int
    list_first: int          # list price of the dealer's first option, cents
    ref_fee: int
    legs: int
    slack_h: float
    drive_h: float
    quote: int | None = None  # our last quote on the first option, cents
    won: bool | None = None   # None: no outcome seen
    trust: int = 0            # the dealer's on-time count when the request arrived


@dataclass
class Booking:
    at: int
    gig: str
    orders: tuple
    fee: int                  # booked fee, cents
    ref: int                  # typical fee of the gig's cars, cents (the requests' referenceFeeCents share)
    opening: int              # first step of the schedule the gig was booked under
    top: int                  # last (highest) step of that schedule
    urgent: bool              # posted or repriced after the order's deadline_close


@dataclass
class RunX:
    world: str
    seed: str
    setting: str
    params: dict
    score: dict
    reqs: dict = field(default_factory=dict)
    bookings: list = field(default_factory=list)
    dclose: list = field(default_factory=list)        # (minute, order id)
    orders: dict = field(default_factory=dict)        # governor_parse Order objects
    fee_cents: int = 0                                 # driver + release fee lines
    revenue_cents: int = 0
    trust_up: int = 0                                  # revenue lines that raised a dealer's count
    trust_halved: int = 0                              # revenue lines with a late refund (halved a count)


def parse(world: str) -> RunX:
    base = gp.parse(world)
    run = RunX(world, base.seed, base.setting, base.params, base.score, orders=base.orders)
    trust: dict[str, int] = {}
    order_dealer: dict[str, str] = {}
    late_orders: set[str] = set()
    pending_rev: dict[str, int] = {}
    gig_sched: dict[str, list] = {}
    gig_orders: dict[str, tuple] = {}
    gig_urgent: dict[str, bool] = {}
    urgent_orders: set[str] = set()
    req_raw: dict[str, dict] = {}

    def settle(before: int) -> None:
        """Apply the revenue lines of minutes before `before` (on time: +1 up to 25, late: halve), in time order.
        A late refund line follows its revenue line in the same minute, so a minute is settled only once a
        later minute starts: a request arriving in that same minute sees the count without it."""
        for oid in [o for o, t in pending_rev.items() if t < before]:
            d = order_dealer.get(oid)
            del pending_rev[oid]
            if d is None:
                continue
            if oid in late_orders:
                trust[d] = trust.get(d, 0) // 2
                run.trust_halved += 1
            else:
                trust[d] = min(TRUST_CAP, trust.get(d, 0) + 1)
                run.trust_up += 1

    for call in load(ROOT / "runs" / world / "journal.jsonl"):
        if call.resp is None or call.op not in ("advance", "act"):
            continue
        at = call.req["at"]
        acts = call.req.get("actions", [])
        results = call.resp["results"] if call.op == "advance" else call.resp
        for a, r in zip(acts, results):
            if a["type"] == "quote" and a["requestId"] in run.reqs:
                rq = req_raw[a["requestId"]]
                first = rq["options"][0]["kind"]
                if first in a["prices"]:
                    run.reqs[a["requestId"]].quote = a["prices"][first]
            elif a["type"] in ("post", "reprice") and r.get("ok"):
                gid = r["id"] if a["type"] == "post" else a["gigId"]
                gig_sched[gid] = a["schedule"]
                if a["type"] == "post":
                    gig_orders[gid] = tuple(sorted({s["orderId"] for s in a["stops"] if s["kind"] == "pickup"}))
                gig_urgent[gid] = any(o in urgent_orders for o in gig_orders.get(gid, ()))
        if call.op != "advance":
            continue
        for e in call.resp["events"]:
            k, t = e["kind"], e["at"]
            settle(t)
            if k == "price_request":
                rq = e["request"]
                req_raw[rq["id"]] = rq
                slack, drive = risk(rq, rq["options"][0])
                run.reqs[rq["id"]] = Req(rq["id"], rq["dealerId"], rq["arrivedAt"], rq["options"][0]["listPriceCents"],
                                         rq["referenceFeeCents"], len(rq["legs"]), slack, drive,
                                         trust=trust.get(rq["dealerId"], 0))
            elif k == "order_won":
                oid = e["order"]["id"]
                order_dealer[oid] = e["order"]["dealerId"]
                if oid in run.reqs:
                    run.reqs[oid].won = True
            elif k == "order_lost":
                if e["requestId"] in run.reqs:
                    run.reqs[e["requestId"]].won = False
            elif k == "deadline_close":
                run.dclose.append((t, e["orderId"]))
                urgent_orders.add(e["orderId"])
            elif k == "gig_booked":
                gid = e["gigId"]
                sched = gig_sched.get(gid, [])
                oids = gig_orders.get(gid, ())
                ref = 0
                for oid in oids:
                    rq = req_raw.get(oid)
                    if rq is not None:
                        ref += rq["referenceFeeCents"]  # starter gigs carry whole orders; legs of one order share it
                run.bookings.append(Booking(t, gid, oids, e["feeCents"], ref,
                                            sched[0]["feeCents"] if sched else 0, sched[-1]["feeCents"] if sched else 0,
                                            gig_urgent.get(gid, False)))
            elif k == "ledger":
                line = e["line"]
                if line["kind"] == "revenue":
                    run.revenue_cents += line["cents"]
                    pending_rev[line["orderId"]] = t
                elif line["kind"] in ("late_refund", "undelivered_penalty"):
                    late_orders.add(line["orderId"])
                elif line["kind"] in ("driver_fee", "release_fee"):
                    run.fee_cents += -line["cents"]
    return run


def load_runs(cache: Path | None = None) -> list[RunX]:
    if cache is not None and cache.exists():
        return pickle.loads(cache.read_bytes())
    runs = [parse(w) for w in gp.RUNS if w not in gp.EXCLUDED and (ROOT / "runs" / w / "summary.json").exists()]
    if cache is not None:
        cache.write_bytes(pickle.dumps(runs))
    return runs


if __name__ == "__main__":
    import sys
    rs = load_runs(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    for r in rs:
        won = sum(1 for q in r.reqs.values() if q.won)
        print(r.world, r.seed, r.setting, len(r.reqs), won, r.score["wonOrders"], len(r.bookings), len(r.dclose))
