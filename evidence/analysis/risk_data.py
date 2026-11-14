"""Won orders of the L8 `priced` runs, with the features known when the request arrived and the outcome.

Read-only: it reads runs/<worldId>/{meta,summary}.json and journal.jsonl and data/map.json; it makes no calls.

    .venv/bin/python -m evidence.analysis.risk_data      # prints the run list and a one-line count per run
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, fields
from pathlib import Path

from desk.policy import Params, risk as policy_risk
from tools.diagnose import events_and_posts

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {"wc721c95a136b417e5d7c"}  # perturbed by a server incident
SEEDS = ("dev-1", "dev-2", "dev-3", "dev-4")
DAY = 1440
BULK_BATCH = 20  # a batch this large is the unannounced bulk order (30-40 cars from one yard)

# Pinned at analysis time (14 Nov 03:00) so every number reproduces after more runs land: every L8 `priced`
# run on dev-1..dev-4 with a summary.json, minus EXCLUDED. `discover()` rebuilds the list from disk.
PINNED = [
    "w00d7fea2fc44422171f7", "w0473b26193b4c625c320", "w058a107aee657ab89d19", "w0de650a7c208a71eae79",
    "w16be63a484d37af7b79f", "w1c284038fc623a84b61e", "w1fcfa35cc90b05b5f1c2", "w243d2cca71b69d253b5c",
    "w28e68c48d83ca64805ee", "w3011bc338409eb5218c4", "w32164cb36bfc94fc8cc5", "w37bde37df83bc9b83dd3",
    "w38b56a8e83c6350d114c", "w38e64407b3bb84092f12", "w3cbdd02bb3358f6f3f61", "w411c3eb3c674c9d1c3d3",
    "w425af5049cb5cd6ad3bd", "w443baa74100a4ec8250e", "w4c43bd2c3320010e4e1d", "w4d8473c66bf47b0aa6e9",
    "w5232432205ca57ee1a03", "w53c4573644e130f9d576", "w58b2f2b7471fa68db9a1", "w68fcc000caab79e6871e",
    "w6d27b004ff2ea1ea3d8b", "w6dc5262674eea563331f", "w6e211bc95ce04cb74838", "w71910f9d1ce6008c1d19",
    "w729ebfd45d6eb00ae70c", "w72c669d6699da8b4e97b", "w73af911f6e4e878c2f88", "w78e12756255e00e5ef83",
    "w7c1b447a9acea1f75e87", "w8c295fc08c474469b96b", "w8efe6d2b3aba4223adf6", "w8f8b336210e98168f6c3",
    "w9316f20563850d387071", "w986051b30df6aaeb7659", "w9e27d15f5b6694d37eeb", "wa403bf0a82f9bcf12409",
    "wa47c23779e51451adba4", "wb22082f87a9589cc2a73", "wb2c897708edf9d86051a", "wba66ccd80b69d5444e19",
    "wcaeeaf13aa0217213e93", "wcc6d7d0124ae31aecd0c", "wd8aa9054e3b4b6188624", "we6aa949e40bc7d753a86",
    "webc48458f1877561affc", "wfb8aafc722d369eb552a", "wfd28315d1cd89e49a0e5",
]


def discover() -> list[str]:
    out = []
    for d in sorted((ROOT / "runs").iterdir()):
        meta_p, sum_p = d / "meta.json", d / "summary.json"
        if d.name in EXCLUDED or not meta_p.exists() or not sum_p.exists():
            continue
        meta = json.loads(meta_p.read_text())
        if meta.get("policy") == "priced" and meta.get("level") == 8 and meta.get("seed") in SEEDS:
            out.append(d.name)
    return out


def full_params(meta: dict) -> dict:
    """The params a run actually played with: defaults filled in, numbers as floats."""
    merged = {**asdict(Params()), **(meta.get("params") or {})}
    return {k: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for k, v in merged.items()}


def dedupe(world_ids: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Worlds are deterministic: the same seed and params replay the same week. Keep one run per (seed, params)."""
    keep, dropped, seen = [], [], {}
    for w in world_ids:
        meta = json.loads((ROOT / "runs" / w / "meta.json").read_text())
        key = (meta["seed"], json.dumps(full_params(meta), sort_keys=True))
        if key in seen:
            dropped.append((w, seen[key]))
        else:
            seen[key] = w
            keep.append(w)
    return keep, dropped


_MAP: dict = {}


def road(a: str, b: str) -> tuple[int, float]:
    if not _MAP:
        roads = json.loads((ROOT / "data" / "map.json").read_text(encoding="utf-8"))["roads"]
        _MAP.update({(r["from"], r["to"]): (r["minutes"], r["km"]) for r in roads})
    return (0, 0.0) if a == b else _MAP[(a, b)]


def _open_interval(day: int, hours: dict) -> tuple[int, int] | None:
    wd = day % 7
    if wd <= 4 and wd in hours["weekdays"]:
        return day * DAY + hours["opens"], day * DAY + hours["closes"]
    if wd == 5 and hours.get("saturday"):
        return day * DAY + hours["saturday"]["opens"], day * DAY + hours["saturday"]["closes"]
    return None


def earliest_open(t: int, hours: dict | None) -> int:
    """First minute >= t at which a site with these stated hours is open (private address: t)."""
    if not hours:
        return t
    for day in range(t // DAY, t // DAY + 10):
        iv = _open_interval(day, hours)
        if iv and t < iv[1]:
            return max(t, iv[0])
    return t


def latest_open(t: int, hours: dict | None) -> int:
    """Last minute <= t at which a site with these stated hours is open (private address: t)."""
    if not hours:
        return t
    for day in range(t // DAY, t // DAY - 10, -1):
        iv = _open_interval(day, hours)
        if iv and iv[0] <= t:
            return min(t, iv[1])
    return t


def request_features(req: dict, forecasts: list[dict], batch_sizes: Counter) -> dict:
    """Everything here is in the price_request (or earlier events) at arrival."""
    opt = req["options"][0]  # the priced policy quotes the dealer's first option only
    slack_h, drive_h = policy_risk(req, opt)
    legs = req["legs"]
    first, last = legs[0], legs[-1]
    ready = max(l["pickup"]["window"]["from"] for l in legs)
    start = max(first["pickup"]["window"]["from"], req["respondBy"])
    start_open = earliest_open(start, None if first["pickup"]["privateAddress"] else first["pickup"]["hours"])
    end_ok = latest_open(opt["deadline"], None if last["delivery"]["privateAddress"] else last["delivery"]["hours"])
    eff_slack_h = (end_ok - start_open - drive_h * 60) / 60
    places = {first["pickup"]["placeId"], last["delivery"]["placeId"]}
    snow = any(f["at"] <= req["arrivedAt"] and f["from"] < opt["deadline"] and f["to"] > ready and places & set(f["placeIds"])
               for f in forecasts)
    km = [road(l["pickup"]["placeId"], l["delivery"]["placeId"])[1] for l in legs]
    low = [l["car"]["electric"] and l["car"]["chargePercent"] is not None and l["car"]["chargePercent"] < 30 for l in legs]
    arrived = req["arrivedAt"]
    return {
        "slack_h": slack_h,
        "eff_slack_h": eff_slack_h,
        "drive_h": drive_h,
        "weekday": arrived // DAY,
        "hour": (arrived % DAY) / 60,
        "kind": opt["kind"],
        "n_options": len(req["options"]),
        "legs": len(legs),
        "private": any(l[s]["privateAddress"] for l in legs for s in ("pickup", "delivery")),
        "priv_pickup": any(l["pickup"]["privateAddress"] for l in legs),
        "priv_delivery": any(l["delivery"]["privateAddress"] for l in legs),
        "premium": any(l["car"]["premium"] for l in legs),
        "ev_low": any(low),
        "ev_low_long": any(x and k > 200 for x, k in zip(low, km)),
        "note": req["note"] is not None,
        "pickup": first["pickup"]["placeId"],
        "delivery": last["delivery"]["placeId"],
        # extras, also known at arrival
        "lead_h": (ready - arrived) / 60,
        "ready_hour": (ready % DAY) / 60,
        "deadline_day": opt["deadline"] // DAY,
        "bulk": req["batchId"] is not None and batch_sizes[req["batchId"]] >= BULK_BATCH,
        "snow": snow,
        "list_cents": opt["listPriceCents"],
        "ref_fee_cents": req["referenceFeeCents"],
        "start_min": start,
        "deadline_min": opt["deadline"],
        "day_slack_h": (daytime_minutes(start, opt["deadline"]) - drive_h * 60) / 60,
        "best_day_slack_h": best_day_slack(start, opt["deadline"], drive_h * 60),
    }


def best_day_slack(a: int, b: int, drive: float) -> float:
    """Slack, in hours, of the best single working day (07:00-20:00, Mon-Fri) between a and b: the most room
    a driver has to do the whole drive inside one day."""
    best = -24.0
    for day in range(a // DAY, b // DAY + 1):
        if day % 7 < 5:
            s, e = max(a, day * DAY + 7 * 60), min(b, day * DAY + 20 * 60)
            best = max(best, (e - s - drive) / 60)
    return best


def daytime_minutes(a: int, b: int, lo: int = 7 * 60, hi: int = 20 * 60) -> int:
    """Minutes of [a, b) that fall between 07:00 and 20:00 on Monday-Friday: the hours a car can move and land."""
    total = 0
    for day in range(a // DAY, b // DAY + 1):
        if day % 7 >= 5:
            continue
        s, e = max(a, day * DAY + lo), min(b, day * DAY + hi)
        total += max(0, e - s)
    return total


def run_rows(world_id: str) -> list[dict]:
    meta = json.loads((ROOT / "runs" / world_id / "meta.json").read_text())
    params = full_params(meta)
    events, posts = events_and_posts(world_id)
    requests = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
    batch_sizes = Counter(r["batchId"] for r in requests.values() if r["batchId"] is not None)
    forecasts = [e for e in events if e["kind"] == "forecast"]
    won = {e["order"]["id"]: e for e in events if e["kind"] == "order_won"}
    cancelled = {e["orderId"] for e in events if e["kind"] == "order_cancelled"}
    gig_orders = {r["id"]: sorted({s["orderId"] for s in a["stops"]}) for _, a, r in posts if r.get("ok")}
    money = defaultdict(lambda: defaultdict(int))
    for e in events:
        if e["kind"] != "ledger":
            continue
        line = e["line"]
        targets = [line["orderId"]] if line["orderId"] else gig_orders.get(line["gigId"], [])
        for o in targets:
            money[o][line["kind"]] += line["cents"] / len(targets)
        if line["kind"] == "revenue":
            money[line["orderId"]]["delivered_at"] = e["at"]
    rows = []
    for oid, ev in won.items():
        if oid in cancelled or oid not in requests:
            continue
        req, order, m = requests[oid], ev["order"], money[oid]
        price = order["priceCents"]
        refund, penalty = -m.get("late_refund", 0), -m.get("undelivered_penalty", 0)
        late = refund > 0 or penalty > 0
        share = 3.0 if penalty > 0 else refund / price  # undelivered: price never paid + 2x penalty
        cost = sum(v for k, v in m.items() if k in ("driver_fee", "failed_visit", "release_fee", "waiting", "fine"))
        rows.append({
            "world": world_id, "seed": meta["seed"], "price_mult": params["price_mult"], "fee_mode": params["fee_mode"],
            "min_slack_h": params["min_slack_h"], "max_drive_h": params["max_drive_h"],
            "order": oid, "won_at": ev["at"], "arrived": req["arrivedAt"], "delivered_at": m.get("delivered_at"),
            "price": price, "option_won": order["option"], "order_deadline": order["deadline"],
            "late": late, "undelivered": penalty > 0, "refund": refund, "penalty": penalty, "loss_share": share,
            "resolved": m.get("delivered_at") is not None or penalty > 0,
            "margin": sum(v for k, v in m.items() if k != "delivered_at"), "cost": -cost,
            **request_features(req, forecasts, batch_sizes),
        })
    # our own book at arrival: orders won earlier that were not yet delivered (known to the desk)
    for r in rows:
        r["book"] = sum(1 for o in rows if o["won_at"] <= r["arrived"]
                        and (o["delivered_at"] is None or o["delivered_at"] > r["arrived"]))
    return rows


def load_rows(world_ids: list[str] | None = None) -> tuple[list[dict], dict]:
    ids = PINNED if world_ids is None else world_ids
    keep, dropped = dedupe(ids)
    rows = [r for w in keep for r in run_rows(w)]
    return rows, {"pinned": len(ids), "kept": keep, "duplicates": dropped}


if __name__ == "__main__":
    found = discover()
    print("discover() now:", len(found), "pinned:", len(PINNED), "not pinned:", sorted(set(found) - set(PINNED)))
    rows, info = load_rows()
    print("kept", len(info["kept"]), "dropped duplicates", info["duplicates"])
    by = defaultdict(list)
    for r in rows:
        by[r["world"]].append(r)
    for w, rs in by.items():
        print(w, rs[0]["seed"], rs[0]["price_mult"], rs[0]["fee_mode"], rs[0]["min_slack_h"], rs[0]["max_drive_h"],
              len(rs), "late", sum(r["late"] for r in rs), "margin", round(sum(r["margin"] for r in rs) / 100))
