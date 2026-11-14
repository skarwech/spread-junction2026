"""Why a played week lost money or on-time share: read from its journal only (no calls to the server).

    python -m tools.diagnose <worldId>
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from desk.journal import load

ROOT = Path(__file__).resolve().parents[1]


def events_and_posts(world_id: str) -> tuple[list, list]:
    events, posts = [], []
    for call in load(ROOT / "runs" / world_id / "journal.jsonl"):
        if call.resp is None:
            continue
        if call.op == "advance":
            events += call.resp["events"]
        acts = call.req.get("actions", []) if isinstance(call.req, dict) else []
        results = call.resp["results"] if call.op == "advance" else call.resp if call.op == "act" else []
        posts += [(call.req["at"], a, r) for a, r in zip(acts, results) if a["type"] == "post"]
    return events, posts


def hash_ids(ids: list) -> str:
    import hashlib
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()[:12]


def diagnose(world_id: str) -> dict:
    events, posts = events_and_posts(world_id)
    requests = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
    won = {e["order"]["id"]: e for e in events if e["kind"] == "order_won"}
    cancelled = {e["orderId"] for e in events if e["kind"] == "order_cancelled"}
    gig_order = {r["id"]: a["stops"][0]["orderId"] for _, a, r in posts if r.get("ok")}
    first_post = {}
    for at, a, r in posts:
        first_post.setdefault(a["stops"][0]["orderId"], at)
    booked_at, booked_fee, deadline_close, refunds, revenue, penalties = {}, {}, set(), defaultdict(int), {}, set()
    expired, failed = Counter(), Counter()
    for e in events:
        oid = gig_order.get(e.get("gigId", ""))
        if e["kind"] == "visit_failed":
            failed[e["orderId"]] += 1
        if e["kind"] == "gig_booked" and oid:
            booked_at.setdefault(oid, e["at"])
            booked_fee[oid] = booked_fee.get(oid, 0) + e["feeCents"]
        elif e["kind"] == "gig_expired" and oid:
            expired[oid] += 1
        elif e["kind"] == "deadline_close":
            deadline_close.add(e["orderId"])
        elif e["kind"] == "ledger":
            line = e["line"]
            if line["kind"] == "late_refund":
                refunds[line["orderId"]] += -line["cents"]
            elif line["kind"] == "revenue":
                revenue[line["orderId"]] = line["cents"]
            elif line["kind"] == "undelivered_penalty":
                penalties.add(line["orderId"])
    orders = [o for o in won if o not in cancelled]
    tiers = Counter()
    for o in orders:
        price = won[o]["order"]["priceCents"]
        if o in penalties:
            tiers["undelivered"] += 1
        elif o not in revenue:
            tiers["not delivered yet"] += 1
        elif not refunds[o]:
            tiers["on time"] += 1
        else:
            share = refunds[o] / price
            tiers["late ≤2 h (10%)" if share < 0.2 else "late 2–24 h (25%)" if share < 0.4 else "late ≤2 bd (50%)" if share < 0.75 else "late >2 bd (100%)"] += 1
    wait_h = sorted((booked_at[o] - first_post[o]) / 60 for o in orders if o in booked_at and o in first_post)
    late = [o for o in orders if o in revenue and refunds[o]]
    late_after_warning = sum(o in deadline_close for o in late)
    fee_ratio = sorted(booked_fee[o] / requests[o]["referenceFeeCents"] for o in orders if o in booked_fee and o in requests)
    price_ratio = sorted(won[o]["order"]["priceCents"] / next(op["listPriceCents"] for op in requests[o]["options"] if op["kind"] == won[o]["order"]["option"]) for o in orders if o in requests)
    q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None
    causes = Counter()
    for o in late + [o for o in orders if o in penalties]:
        last_pickup = won[o]["order"]["lastPickupAt"]
        causes["failed visit" if failed[o] else "booked after lastPickupAt" if booked_at.get(o, 10**9) > last_pickup
               else "gig expired first" if expired[o] else "booked in time, still late"] += 1
    margin = sum(e["line"]["cents"] for e in events if e["kind"] == "ledger")
    return {
        "marginCents": margin,
        "lateCauses": dict(causes.most_common()),
        "requestIdsDigest": hash_ids(sorted(requests)),
        "requests": len(requests), "won": len(orders), "winRate": len(orders) / len(requests),
        "outcomes": dict(tiers.most_common()),
        "neverBooked": sum(o not in booked_at for o in orders),
        "hoursPostToBooking": {"p50": q(wait_h, .5), "p75": q(wait_h, .75), "p90": q(wait_h, .9)},
        "lateOrdersThatGotDeadlineWarning": f"{late_after_warning}/{len(late)}",
        "ordersWithExpiredGig": sum(1 for o in orders if expired[o]),
        "bookedFeeOverTypicalFee": {"p50": q(fee_ratio, .5), "p90": q(fee_ratio, .9)},
        "priceOverList": {"p50": q(price_ratio, .5), "max": price_ratio[-1] if price_ratio else None},
    }


if __name__ == "__main__":
    print(json.dumps(diagnose(sys.argv[1]), indent=1, ensure_ascii=False))
