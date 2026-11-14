"""Independent data layer for the review of risk.md (it shares no code with risk_data.py / risk.py).

Read-only: runs/<worldId>/{meta,summary}.json, journal.jsonl and data/map.json. No network, no worlds.
Every feature is computed from what the desk had seen at the request's arrival minute ("known at t"),
and, side by side, the way risk.py computes it, so the two can be compared.
"""
from __future__ import annotations

import bisect
import json
import math
from collections import defaultdict
from pathlib import Path

from desk.journal import load

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {"wc721c95a136b417e5d7c"}  # server incident (task statement)
DEV = ("dev-1", "dev-2", "dev-3", "dev-4")
HOLD = ("hold-1", "hold-2", "hold-3", "hold-4", "hold-5", "hold-6")
DAY = 1440
DEFAULTS = {"price_mult": 1.0, "fee_mode": "starter", "min_slack_h": -999.0, "max_drive_h": 999.0}

_ROADS: dict[tuple[str, str], int] = {}


def road_min(a: str, b: str) -> int:
    """Road minutes from the public map; a same-place leg counts 0, as desk.policy.risk() does."""
    if not _ROADS:
        for r in json.loads((ROOT / "data" / "map.json").read_text(encoding="utf-8"))["roads"]:
            _ROADS[(r["from"], r["to"])] = r["minutes"]
    return 0 if a == b else _ROADS[(a, b)]


def select_runs() -> tuple[list[dict], dict]:
    """L8 `priced` runs on the dev and hold seeds that have a summary.json, minus EXCLUDED. Duplicates are
    found by the server's fingerprint (an identical week), not by params."""
    found, skipped, seen, dups = [], [], {}, []
    for d in sorted((ROOT / "runs").iterdir()):
        if not d.is_dir():
            continue
        if d.name in EXCLUDED:
            skipped.append((d.name, "excluded"))
            continue
        sp, mp = d / "summary.json", d / "meta.json"
        if not sp.exists() or not mp.exists():
            meta = json.loads(mp.read_text()) if mp.exists() else {}
            if meta.get("seed") in DEV + HOLD:
                skipped.append((d.name, "no summary.json"))
            continue
        s = json.loads(sp.read_text())
        if s.get("level") != 8 or s.get("policy") != "priced" or s.get("seed") not in DEV + HOLD:
            continue
        if s["days"][-1]["label"] != "End":
            skipped.append((d.name, "week not ended"))
            continue
        params = {**DEFAULTS, **(s.get("params") or {})}
        key = (s["seed"], s.get("fingerprint"))
        if key in seen:
            dups.append((d.name, seen[key]))
            continue
        seen[key] = d.name
        end = s["days"][-1]["score"]
        found.append({"world": d.name, "seed": s["seed"], "params": params,
                      "regime_r": float(params["price_mult"]) == 1.5 and params["fee_mode"] == "deadline",
                      "unfiltered": float(params["min_slack_h"]) < -100 and float(params["max_drive_h"]) > 100,
                      "server_margin": end["marginCents"], "server_ontime": end["onTimeShare"],
                      "server_won": end["wonOrders"], "server_ranked": end["ranked"]})
    return found, {"skipped": skipped, "duplicates": dups}


def best_day_slack_h(start: int, deadline: int, drive_min: float) -> float:
    """Most spare hours in one working day (Mon-Fri 07:00-20:00) between start and deadline, after the drive."""
    best = -24.0
    for day in range(start // DAY, deadline // DAY + 1):
        if day % 7 >= 5:
            continue
        lo, hi = max(start, day * DAY + 420), min(deadline, day * DAY + 1200)
        best = max(best, (hi - lo - drive_min) / 60)
    return best


def request_features(req: dict) -> dict:
    opt = req["options"][0]  # the priced policy quotes the dealer's first option only
    legs = req["legs"]
    drive = sum(road_min(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
    ready = max(max(l["pickup"]["window"]["from"] for l in legs), req["respondBy"])
    start = max(legs[0]["pickup"]["window"]["from"], req["respondBy"])
    return {
        "arrived": req["arrivedAt"], "kind": opt["kind"], "deadline_opt": opt["deadline"],
        "drive_h": drive / 60,
        "task_slack_h": (opt["deadline"] - ready - drive) / 60,
        "bds_h": best_day_slack_h(start, opt["deadline"], drive),
        "two_legs": len(legs) == 2,
        "priv_pickup": any(l["pickup"]["privateAddress"] for l in legs),
        "priv_delivery": any(l["delivery"]["privateAddress"] for l in legs),
        "premium": any(l["car"]["premium"] for l in legs),
        "note": req.get("note") is not None,
        "town": legs[0]["pickup"]["placeId"],
    }


def parse_run(run: dict) -> list[dict]:
    """One row per won order (cancelled ones flagged), with label, money and known-at-arrival features."""
    events, seqs = [], set()
    for c in load(ROOT / "runs" / run["world"] / "journal.jsonl"):
        if c.op == "advance" and c.resp is not None:
            for e in c.resp["events"]:
                if e["seq"] not in seqs:
                    seqs.add(e["seq"])
                    events.append(e)
    events.sort(key=lambda e: e["seq"])
    reqs, won, deadlines, cancel_at, rev_at, refund_at = {}, {}, defaultdict(list), {}, {}, {}
    money, refund, penalty, ledger_total = defaultdict(int), defaultdict(int), defaultdict(int), 0
    for e in events:
        k = e["kind"]
        if k == "price_request":
            reqs[e["request"]["id"]] = e["request"]
        elif k == "order_won":
            won[e["order"]["id"]] = (e["at"], e["order"])
            deadlines[e["order"]["id"]].append((e["at"], e["order"]["deadline"]))
        elif k == "order_changed":
            deadlines[e["order"]["id"]].append((e["at"], e["order"]["deadline"]))
        elif k == "order_cancelled":
            cancel_at[e["orderId"]] = e["at"]
        elif k == "ledger":
            line = e["line"]
            ledger_total += line["cents"]
            oid = line["orderId"]
            if oid is None:
                raise ValueError(f"{run['world']}: ledger line without orderId: {line}")
            money[oid] += line["cents"]
            if line["kind"] == "revenue":
                rev_at[oid] = e["at"]
            elif line["kind"] == "late_refund":
                refund[oid] += -line["cents"]
                refund_at.setdefault(oid, e["at"])
            elif line["kind"] == "undelivered_penalty":
                penalty[oid] += -line["cents"]
    run["ledger_total"] = ledger_total

    # Known-at-t state, built from every won order (cancelled ones count until their cancellation).
    orders = []
    for oid, (wat, order) in won.items():
        final_deadline = deadlines[oid][-1][1]
        delivered = rev_at.get(oid)
        orders.append({"id": oid, "won_at": wat, "deadline_won": order["deadline"], "final_deadline": final_deadline,
                       "deadline_moved": final_deadline != order["deadline"], "delivered_at": delivered,
                       "refund_at": refund_at.get(oid), "cancel_at": cancel_at.get(oid),
                       "town": reqs[oid]["legs"][0]["pickup"]["placeId"]})
    won_times = sorted(o["won_at"] for o in orders)
    end_times = sorted(min(x for x in (o["delivered_at"], o["cancel_at"]) if x is not None)
                       for o in orders if o["delivered_at"] is not None or o["cancel_at"] is not None)
    by_deadline = sorted(orders, key=lambda o: o["deadline_won"])
    dl_keys = [o["deadline_won"] for o in by_deadline]

    rows = []
    for o in orders:
        oid = o["id"]
        wat, order = won[oid]
        req = reqs[oid]
        t = req["arrivedAt"]
        f = request_features(req)
        # open orders known at t: won by t, neither delivered nor cancelled by t
        book = bisect.bisect_right(won_times, t) - bisect.bisect_right(end_times, t)
        # own late share known at t: orders whose deadline (as known at t) has passed, not cancelled by t;
        # late iff not delivered by t, or a late_refund line came by t (a private delivery's own deadline is
        # earlier than the order's, so a refund can come before the order deadline)
        mat = late = 0
        mat_town = late_town = 0
        for p in by_deadline[:bisect.bisect_left(dl_keys, t)]:
            if p["cancel_at"] is not None and p["cancel_at"] <= t:
                continue
            dl = [d for at, d in deadlines[p["id"]] if at <= t][-1]
            if dl >= t:
                continue
            is_late = (p["delivered_at"] is None or p["delivered_at"] > t
                       or (p["refund_at"] is not None and p["refund_at"] <= t))
            mat += 1
            late += is_late
            if p["town"] == f["town"]:
                mat_town += 1
                late_town += is_late
        s = (late + 1.5) / (mat + 10)
        s_town = (late_town + 5 * s) / (mat_town + 5)
        price = order["priceCents"]
        resolved = oid in rev_at or penalty[oid] > 0
        lab = refund[oid] > 0 or penalty[oid] > 0
        rows.append({
            "world": run["world"], "seed": run["seed"], "regime_r": run["regime_r"], "unfiltered": run["unfiltered"],
            "order": oid, "won_at": wat, "delivered_at": rev_at.get(oid), "cancelled": oid in cancel_at,
            "cancel_at": cancel_at.get(oid), "deadline_won": order["deadline"], "final_deadline": o["final_deadline"],
            "deadline_moved": o["deadline_moved"], "price": price, "margin": money[oid],
            "refund": refund[oid], "penalty": penalty[oid], "resolved": resolved,
            # server rule: a car not delivered when the world ends counts as late
            "late": lab or not resolved, "late_ledger": lab,
            "late_by_time": rev_at.get(oid) is None or rev_at[oid] > o["final_deadline"],
            "book": book, "s": s, "s_town": s_town, "matured": mat,
            **f,
        })
    return rows


def add_analyst_style_state(rows: list[dict]) -> None:
    """The state features the way risk.py builds them, for comparison: over the kept rows only (never-cancelled,
    resolved, not within_3_days), using each order's FINAL late label and its order_won deadline."""
    by_world = defaultdict(list)
    for r in rows:
        by_world[r["world"]].append(r)
    for rs in by_world.values():
        kept = [r for r in rs if not r["cancelled"] and r["resolved"] and r["kind"] != "within_3_days"]
        for r in rs:
            t = r["arrived"]
            r["book_a"] = sum(1 for o in kept if o["won_at"] <= t and (o["delivered_at"] is None or o["delivered_at"] > t))
            mat = [o for o in kept if o["deadline_won"] < t]
            s = (sum(o["late_ledger"] for o in mat) + 1.5) / (len(mat) + 10)
            town = [o for o in mat if o["town"] == r["town"]]
            r["s_a"] = s
            r["s_town_a"] = (sum(o["late_ledger"] for o in town) + 5 * s) / (len(town) + 5)


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def f_features(r: dict, book: float | None = None, s: float | None = None, s_town: float | None = None,
               style: str = "known") -> list[float]:
    """Model F's ten terms, in the order of the recommendation's formula."""
    if style == "analyst":
        book = r["book_a"] if book is None else book
        s = r["s_a"] if s is None else s
        s_town = r["s_town_a"] if s_town is None else s_town
    else:
        book = r["book"] if book is None else book
        s = r["s"] if s is None else s
        s_town = r["s_town"] if s_town is None else s_town
    return [max(0.0, 10 - r["bds_h"]), min(r["drive_h"], 10.0), float(r["two_legs"]), float(r["priv_pickup"]),
            float(r["priv_delivery"]), float(r["premium"]), float(r["note"]), math.log1p(book), logit(s),
            logit(s_town) - logit(s)]


F_NAMES = ["max(0,10-bds_h)", "min(drive_h,10)", "two legs", "private pickup", "private delivery", "premium",
           "note", "ln(1+open orders)", "logit(s)", "logit(s_town)-logit(s)"]
