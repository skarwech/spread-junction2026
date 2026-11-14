"""Order timelines for the volume governor, read from recorded journals only (no calls to the server).

    .venv/bin/python -m evidence.analysis.governor_parse      # prints one line per pinned run

For every won (not cancelled) order of a run: when its request arrived, when it was won, first posted, first
fully held by drivers, finished; every minute its "held" state changed; whether it ended late (a late_refund or
undelivered_penalty line) and its own P&L (its ledger lines plus its share of its gigs' fees). Also every
request (to replay other decisions on the same seed), every booking and every deadline_close.

An order is "held" at minute t when every undelivered leg sits in a gig that a driver has booked or started.
"""
from __future__ import annotations

import json
import pickle
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from desk.journal import load
from desk.policy import risk

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {"wc721c95a136b417e5d7c"}  # perturbed by a server incident
HOUR, DAY = 60, 1440

# Pinned 14 Nov 2026 ~05:30 so every number reproduces after more runs land: every level-8 `priced` run on
# dev-1..4 and hold-1..6 with a summary.json, minus EXCLUDED, one per identical (seed, params) setting (the
# deterministic duplicates w6e211bc95ce04cb74838 = w0473b26193b4c625c320, w6dc5262674eea563331f =
# w1fcfa35cc90b05b5f1c2, w3cbdd02bb3358f6f3f61 = w38e64407b3bb84092f12, w37bde37df83bc9b83dd3 =
# w1c284038fc623a84b61e and w58b2f2b7471fa68db9a1 = w16be63a484d37af7b79f are dropped; same scores to the
# cent). w261959b3625349041cf2 has no summary.json.
RUNS = [
    # dev-1
    "wba66ccd80b69d5444e19", "w443baa74100a4ec8250e", "wb22082f87a9589cc2a73", "w058a107aee657ab89d19",
    "w1fcfa35cc90b05b5f1c2", "w8f8b336210e98168f6c3", "w53c4573644e130f9d576", "wb2c897708edf9d86051a",
    "wcc6d7d0124ae31aecd0c", "wfb8aafc722d369eb552a", "w0473b26193b4c625c320", "we6aa949e40bc7d753a86",
    "w243d2cca71b69d253b5c",
    # dev-2
    "w28e68c48d83ca64805ee", "w4d8473c66bf47b0aa6e9", "w38e64407b3bb84092f12", "w4c43bd2c3320010e4e1d",
    "w16be63a484d37af7b79f", "w411c3eb3c674c9d1c3d3", "w38b56a8e83c6350d114c", "w00d7fea2fc44422171f7",
    "wa47c23779e51451adba4", "wa403bf0a82f9bcf12409", "w1c284038fc623a84b61e", "wcaeeaf13aa0217213e93",
    "w68fcc000caab79e6871e",
    # dev-3
    "w3011bc338409eb5218c4", "w425af5049cb5cd6ad3bd", "w7c1b447a9acea1f75e87", "w9316f20563850d387071",
    "wd8aa9054e3b4b6188624", "w986051b30df6aaeb7659", "wfd28315d1cd89e49a0e5", "w71910f9d1ce6008c1d19",
    "w32164cb36bfc94fc8cc5", "w73af911f6e4e878c2f88",
    # dev-4
    "w8efe6d2b3aba4223adf6", "w78e12756255e00e5ef83", "w5232432205ca57ee1a03", "w0de650a7c208a71eae79",
    "webc48458f1877561affc", "w9e27d15f5b6694d37eeb", "w8c295fc08c474469b96b", "w6d27b004ff2ea1ea3d8b",
    "w729ebfd45d6eb00ae70c", "w72c669d6699da8b4e97b",
    # hold-1 .. hold-6: no selection, min_slack_h=4 max_drive_h=5, min_slack_h=6 max_drive_h=5
    "wb1fd6f568123c7c17f54", "wbd2ee97d7536a679a5d8", "w8ca4f470083e84b2e71e",
    "w879a3d155f64e646d7d1", "w65b39bae2860de2bcb23", "w3330bb6305399cfce674",
    "wb9035c91670e517859d1", "wf94c3a185b7c7edacfe3", "w1e3bbbe2181bbab6b71e",
    "wf275f9c05bf437789405", "wa0067bc996bb1b5b865b", "w9092eceae0d66c1c9230",
    "wc69e73feb96e6f9072b2", "w54f8eed3566b8f8d5c0c", "w2be6bf3133a7eb751f8e",
    "w052ee407759a6feff382", "w3141bd32f5c368ffb841", "w02aa24a2ae3cacf98273",
]


@dataclass
class Order:
    id: str
    arrived: int              # request arrivedAt: the minute the quote decision is made
    won_at: int
    price: int
    legs: int
    pickup: str               # first leg's pickup place
    ready: int                # latest pickup window start of the legs
    last_pickup: int          # lastPickupAt in order_won
    deadline: int
    slack_h: float            # desk.policy.risk on the first option, as the selection filter sees it
    drive_h: float
    late: bool = False
    undelivered: bool = False
    pnl: int = 0              # cents: revenue, refunds, penalty, failed visits, fines, waiting, its share of fees
    net_rev: int = 0          # cents: revenue + late_refund + undelivered_penalty lines (they all scale with the price)
    first_post: int | None = None
    first_held: int | None = None
    done_at: int | None = None
    transitions: list = field(default_factory=list)   # (minute, held) on every change
    dc: list = field(default_factory=list)            # deadline_close minutes


@dataclass
class Run:
    world: str
    seed: str
    setting: str
    params: dict
    score: dict               # server score at the end
    orders: dict              # id -> Order (cancelled orders left out)
    requests: dict            # id -> (arrivedAt, first pickup place, slack_h, drive_h, first option list price)
    won_ids: set              # every request won, cancelled included
    bookings: list            # (minute, order id, minutes since the order's first post) on first full hold
    deadline_close: list      # (minute, order id)


def setting_of(params: dict) -> str:
    fee = params.get("fee_mode", "starter")
    sel = ""
    if params.get("min_slack_h", -999) > -900 or params.get("max_drive_h", 999) < 900:
        sel = f" slack>={params.get('min_slack_h', -999):g} drive<={params.get('max_drive_h', 999):g}"
    return f"x{params.get('price_mult', 1.0):g} {fee}{sel}"


def parse(world: str) -> Run:
    folder = ROOT / "runs" / world
    meta = json.loads((folder / "meta.json").read_text())
    score = json.loads((folder / "summary.json").read_text())["days"][-1]["score"]
    orders: dict[str, Order] = {}
    req_obj: dict[str, dict] = {}
    won_ids, cancelled = set(), set()
    gig_legs: dict[str, list] = {}       # gig -> [(order, leg)] it still carries
    gig_state: dict[str, str] = {}       # open | booked | started | gone
    delivered: dict[str, set] = defaultdict(set)
    held: dict[str, bool] = {}
    bookings, dclose = [], []
    fee_lines: list = []                 # (gig, cents) for driver_fee and release_fee lines

    def holders_ok(oid: str) -> bool:
        o = orders[oid]
        need = {leg for leg in range(o.legs) if leg not in delivered[oid]}
        for gid, legs in gig_legs.items():
            if gig_state.get(gid) in ("booked", "started"):
                need -= {leg for (goid, leg) in legs if goid == oid}
        return not need

    def update(oid: str, t: int) -> None:
        o = orders.get(oid)
        if o is None or oid in cancelled or o.done_at is not None:
            return
        now = holders_ok(oid)
        if held.get(oid) != now:
            held[oid] = now
            o.transitions.append((t, now))
            if now and o.first_held is None:
                o.first_held = t
                bookings.append((t, oid, t - (o.first_post if o.first_post is not None else o.won_at)))

    def orders_of(gid: str) -> set:
        return {oid for oid, _ in gig_legs.get(gid, [])}

    gig_cars: dict[str, dict] = {}       # gig -> {order: cars} as posted, for splitting its fee
    for call in load(folder / "journal.jsonl"):
        if call.resp is None or call.op not in ("advance", "act"):
            continue
        at = call.req["at"]
        acts = call.req.get("actions", [])
        results = call.resp["results"] if call.op == "advance" else call.resp
        for a, r in zip(acts, results):
            if a["type"] == "post" and r.get("ok"):
                gid = r["id"]
                gig_legs[gid] = [(s["orderId"], s["leg"]) for s in a["stops"] if s["kind"] == "pickup"]
                cars: dict[str, int] = defaultdict(int)
                for oid, _ in gig_legs[gid]:
                    cars[oid] += 1
                gig_cars[gid] = dict(cars)
                gig_state[gid] = "open"
                for oid in cars:
                    if oid in orders and orders[oid].first_post is None:
                        orders[oid].first_post = at
            elif a["type"] == "withdraw" and r.get("ok") and gig_state.get(a["gigId"]) == "open":
                gig_state[a["gigId"]] = "gone"
            elif a["type"] == "release" and r.get("ok"):
                gig_state[a["gigId"]] = "gone"
                for oid in orders_of(a["gigId"]):
                    update(oid, at)
        if call.op != "advance":
            continue
        for e in call.resp["events"]:
            k, t = e["kind"], e["at"]
            if k == "price_request":
                req_obj[e["request"]["id"]] = e["request"]
            elif k == "order_won":
                od = e["order"]
                rq = req_obj[od["id"]]
                won_ids.add(od["id"])
                slack, drive = risk(rq, rq["options"][0])
                orders[od["id"]] = Order(
                    od["id"], rq["arrivedAt"], t, od["priceCents"], len(od["legs"]), od["legs"][0]["pickup"]["placeId"],
                    max(l["pickup"]["window"]["from"] for l in od["legs"]), od["lastPickupAt"], od["deadline"], slack, drive)
                held[od["id"]] = False
                orders[od["id"]].transitions.append((t, False))
            elif k == "order_cancelled":
                cancelled.add(e["orderId"])
                for g in e.get("gigs", []):
                    if g["outcome"] in ("withdrawn", "released"):
                        gig_state[g["gigId"]] = "gone"
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
                update(e["orderId"], t)
            elif k == "delivered":
                delivered[e["orderId"]].add(e["leg"])
                o = orders.get(e["orderId"])
                if o and len(delivered[e["orderId"]]) >= o.legs and o.done_at is None:
                    o.done_at = t
                    o.transitions.append((t, True))
            elif k == "deadline_close":
                dclose.append((t, e["orderId"]))
                if e["orderId"] in orders:
                    orders[e["orderId"]].dc.append(t)
            elif k == "ledger":
                line = e["line"]
                if line["kind"] in ("driver_fee", "release_fee") and line.get("gigId"):
                    fee_lines.append((line["gigId"], line["cents"]))
                elif line.get("orderId") in orders:
                    o = orders[line["orderId"]]
                    o.pnl += line["cents"]
                    if line["kind"] in ("revenue", "late_refund", "undelivered_penalty"):
                        o.net_rev += line["cents"]
                    if line["kind"] in ("late_refund", "undelivered_penalty"):
                        o.late = True
                        o.undelivered |= line["kind"] == "undelivered_penalty"
            touched = {e.get("orderId")} | orders_of(e.get("gigId") or "")
            for oid in touched - {None}:
                update(oid, t)
    for gid, cents in fee_lines:
        cars = gig_cars.get(gid, {})
        total = sum(cars.values())
        for oid, n in cars.items():
            if oid in orders:
                orders[oid].pnl += round(cents * n / total)
    live = {oid: o for oid, o in orders.items() if oid not in cancelled}
    requests = {}
    for rid, rq in req_obj.items():
        slack, drive = risk(rq, rq["options"][0])
        requests[rid] = (rq["arrivedAt"], rq["legs"][0]["pickup"]["placeId"], slack, drive, rq["options"][0]["listPriceCents"])
    return Run(world, meta["seed"], setting_of(meta.get("params") or {}), meta.get("params") or {}, score, live,
               requests, won_ids, sorted(bookings), sorted(dclose))


def load_runs(cache: Path | None = None) -> list[Run]:
    if cache is not None and cache.exists():
        return pickle.loads(cache.read_bytes())
    runs = [parse(w) for w in RUNS if w not in EXCLUDED and (ROOT / "runs" / w / "summary.json").exists()]
    if cache is not None:
        cache.write_bytes(pickle.dumps(runs))
    return runs


def held_at(o: Order, t: int) -> bool:
    """The order's held state at minute t (False before it was won)."""
    state = False
    for m, h in o.transitions:
        if m > t:
            break
        state = h
    return state


def open_at(o: Order, t: int) -> bool:
    """Won by minute t and not yet finished."""
    return o.won_at <= t and (o.done_at is None or t < o.done_at)


if __name__ == "__main__":
    for run in load_runs():
        late = sum(o.late for o in run.orders.values())
        n = len(run.orders)
        margin = sum(o.pnl for o in run.orders.values())
        print(f"{run.world} {run.seed:<7} {run.setting:<34} won {n:>4} (server {run.score['wonOrders']:>4}) "
              f"on time {1 - late / n:.3f} (server {run.score['onTimeShare']:.3f}) "
              f"order P&L {margin / 100:>10.2f} (server margin {run.score['marginCents'] / 100:>10.2f})")
