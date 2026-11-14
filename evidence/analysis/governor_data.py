"""Order timelines read from recorded journals only (no calls to the server). Used by governor.py.

For each won order: when it was won, whether it ended late (a late_refund or undelivered_penalty line),
its lastPickupAt, its slack and driving time at quote time, and the minutes in which it had no driver
holding every undelivered car (the "backlog" state). Also deadline_close times and booking times.
"""
from __future__ import annotations

import json
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from desk.journal import load  # noqa: E402
from desk.policy import risk  # noqa: E402

DAY, HOUR = 1440, 60
EXCLUDED = {"wc721c95a136b417e5d7c"}  # perturbed by a server incident

# Frozen list: every level-8 dev-seed run with summary.json on 2026-11-14 ~03:10, one per identical
# (seed, policy, params) setting (deterministic duplicates dropped), wc721c95a136b417e5d7c excluded.
RUNS = [
    # dev-1
    "wba66ccd80b69d5444e19", "w443baa74100a4ec8250e", "wb22082f87a9589cc2a73", "w6dc5262674eea563331f",
    "w0473b26193b4c625c320", "w243d2cca71b69d253b5c",  # starter fees 1.0 1.2 1.35 1.5 1.65 1.8
    "w058a107aee657ab89d19", "w8f8b336210e98168f6c3", "we6aa949e40bc7d753a86",  # deadline fees 1.35 1.5 1.65
    "w53c4573644e130f9d576", "wb2c897708edf9d86051a", "wcc6d7d0124ae31aecd0c", "wfb8aafc722d369eb552a",  # select1
    # dev-2
    "w28e68c48d83ca64805ee", "w4d8473c66bf47b0aa6e9", "w38e64407b3bb84092f12", "w58b2f2b7471fa68db9a1",
    "w1c284038fc623a84b61e", "w68fcc000caab79e6871e",
    "w4c43bd2c3320010e4e1d", "w411c3eb3c674c9d1c3d3", "wcaeeaf13aa0217213e93",
    "w38b56a8e83c6350d114c", "w00d7fea2fc44422171f7", "wa47c23779e51451adba4", "wa403bf0a82f9bcf12409",
    # dev-3
    "w3011bc338409eb5218c4", "w7c1b447a9acea1f75e87", "w32164cb36bfc94fc8cc5",
    "w425af5049cb5cd6ad3bd", "w9316f20563850d387071", "w73af911f6e4e878c2f88",
    "wd8aa9054e3b4b6188624", "w986051b30df6aaeb7659", "wfd28315d1cd89e49a0e5", "w71910f9d1ce6008c1d19",
    # dev-4
    "w8efe6d2b3aba4223adf6", "w5232432205ca57ee1a03", "w729ebfd45d6eb00ae70c",
    "w78e12756255e00e5ef83", "w0de650a7c208a71eae79", "w72c669d6699da8b4e97b",
    "webc48458f1877561affc", "w9e27d15f5b6694d37eeb", "w8c295fc08c474469b96b", "w6d27b004ff2ea1ea3d8b",
]


@dataclass
class OrderRec:
    id: str
    won_at: int
    price: int
    list_price: int
    legs: int
    last_pickup: int          # lastPickupAt in order_won
    deadline: int
    slack_h: float            # deadline − max(ready, respondBy) − driving, hours (desk.policy.risk)
    drive_h: float
    late: bool = False        # late_refund or undelivered_penalty line
    undelivered: bool = False
    cancelled: bool = False
    first_post: int | None = None
    first_book: int | None = None
    done_at: int | None = None  # last leg delivered
    # (minute, covered) transitions: covered = a driver holds every undelivered car
    transitions: list = field(default_factory=list)


@dataclass
class RunRec:
    world: str
    seed: str
    label: str
    final: dict
    orders: dict
    requests: dict            # request id -> arrivedAt
    request_list: dict        # request id -> list price of first option
    deadline_close: list      # minutes
    bookings: list            # (minute, order id, minutes since the order's first post)


def setting_label(meta: dict) -> str:
    p = meta.get("params") or {}
    fee = p.get("fee_mode", "starter")
    extra = "".join(f" {k}={p[k]:g}" for k in ("min_slack_h", "max_drive_h") if k in p and p[k] < 900)
    return f"{fee} x{p.get('price_mult', 1.0):g}{extra}"


def _calls(world: str):
    return load(ROOT / "runs" / world / "journal.jsonl")


def parse(world: str) -> RunRec:
    folder = ROOT / "runs" / world
    meta = json.loads((folder / "meta.json").read_text())
    summary = json.loads((folder / "summary.json").read_text())
    orders: dict[str, OrderRec] = {}
    requests, req_obj = {}, {}
    gig_legs: dict[str, list] = {}
    gig_state: dict[str, str] = {}   # open | booked | started | gone
    delivered_legs: dict[str, set] = {}
    covered: dict[str, bool] = {}
    deadline_close, bookings = [], []

    def update(oid: str, t: int) -> None:
        o = orders.get(oid)
        if o is None or o.cancelled or o.done_at is not None:
            return
        need = [leg for leg in range(o.legs) if leg not in delivered_legs.get(oid, set())]
        holders = {leg: False for leg in need}
        for gid, legs in gig_legs.items():
            if gig_state.get(gid) in ("booked", "started"):
                for (goid, leg) in legs:
                    if goid == oid and leg in holders:
                        holders[leg] = True
        now = all(holders.values()) if need else True
        if covered.get(oid) != now:
            covered[oid] = now
            o.transitions.append((t, now))
            if now and o.first_book is None:
                o.first_book = t
                bookings.append((t, oid, t - (o.first_post if o.first_post is not None else o.won_at)))

    def orders_of(gid: str) -> set:
        return {oid for oid, _ in gig_legs.get(gid, [])}

    for call in _calls(world):
        if call.resp is None or call.op not in ("advance", "act"):
            continue
        at = call.req["at"]
        acts = call.req.get("actions", [])
        results = call.resp["results"] if call.op == "advance" else call.resp
        for a, r in zip(acts, results):
            if a["type"] == "post" and r.get("ok"):
                gid = r["id"]
                gig_legs[gid] = [(s["orderId"], s["leg"]) for s in a["stops"] if s["kind"] == "pickup"]
                gig_state[gid] = "open"
                for oid in orders_of(gid):
                    if oid in orders and orders[oid].first_post is None:
                        orders[oid].first_post = at
            elif a["type"] == "withdraw" and r.get("ok", True) and gig_state.get(a["gigId"]) == "open":
                gig_state[a["gigId"]] = "gone"
        if call.op != "advance":
            continue
        for e in call.resp["events"]:
            k, t = e["kind"], e["at"]
            if k == "price_request":
                rq = e["request"]
                requests[rq["id"]] = rq["arrivedAt"]
                req_obj[rq["id"]] = rq
            elif k == "order_won":
                od = e["order"]
                rq = req_obj[od["id"]]
                opt = next(op for op in rq["options"] if op["kind"] == od["option"])
                slack, drive = risk(rq, rq["options"][0])
                orders[od["id"]] = OrderRec(od["id"], t, od["priceCents"], opt["listPriceCents"], len(od["legs"]),
                                            od["lastPickupAt"], od["deadline"], slack, drive)
                covered[od["id"]] = False
                orders[od["id"]].transitions.append((t, False))
            elif k == "order_cancelled":
                if e["orderId"] in orders:
                    orders[e["orderId"]].cancelled = True
                for g in e.get("gigs", []):
                    gig_state[g["gigId"]] = "gone" if g["outcome"] in ("withdrawn", "released") else gig_state.get(g["gigId"], "gone")
            elif k == "gig_booked":
                gig_state[e["gigId"]] = "booked"
            elif k == "gig_started":
                gig_state[e["gigId"]] = "started"
            elif k in ("gig_dropped", "no_show"):
                gig_state[e["gigId"]] = "open"
            elif k == "gig_expired":
                gig_state[e["gigId"]] = "gone"
            elif k == "visit_failed":
                gig_legs[e["gigId"]] = [x for x in gig_legs.get(e["gigId"], []) if x != (e["orderId"], e["leg"])]
            elif k == "delivered":
                delivered_legs.setdefault(e["orderId"], set()).add(e["leg"])
                o = orders.get(e["orderId"])
                if o and len(delivered_legs[e["orderId"]]) >= o.legs and o.done_at is None:
                    o.done_at = t
                    o.transitions.append((t, True))
            elif k == "deadline_close":
                deadline_close.append(t)
            elif k == "ledger":
                line = e["line"]
                o = orders.get(line.get("orderId"))
                if o and line["kind"] in ("late_refund", "undelivered_penalty"):
                    o.late = True
                    o.undelivered |= line["kind"] == "undelivered_penalty"
            for oid in ({e.get("orderId")} | orders_of(e.get("gigId", ""))) - {None}:
                update(oid, t)
    live = {oid: o for oid, o in orders.items() if not o.cancelled}
    first_list = {rid: rq["options"][0]["listPriceCents"] for rid, rq in req_obj.items()}
    return RunRec(world, meta["seed"], setting_label(meta), summary["days"][-1]["score"], live, requests, first_list,
                  sorted(deadline_close), sorted(bookings))


def load_runs(cache: Path | None = None) -> list[RunRec]:
    if cache and cache.exists():
        return pickle.loads(cache.read_bytes())
    runs = [parse(w) for w in RUNS if w not in EXCLUDED and (ROOT / "runs" / w / "summary.json").exists()]
    if cache:
        cache.write_bytes(pickle.dumps(runs))
    return runs


def uncovered_at(o: OrderRec, t: int) -> bool:
    """True when at minute t the order is won, not finished and no driver holds all its undelivered cars."""
    if t < o.won_at or (o.done_at is not None and t >= o.done_at):
        return False
    state = False
    for (m, cov) in o.transitions:
        if m > t:
            break
        state = cov
    return not state
