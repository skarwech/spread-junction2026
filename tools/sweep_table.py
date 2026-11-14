"""Prints a sweep's arms side by side: ranked weeks, margin, worst on-time share, orders, per seed margins.

    python -m tools.sweep_table evidence/sweeps/push1.json [--base "<common prefix to hide>"]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict


def table(path: str) -> list[dict]:
    data = json.loads(open(path, encoding="utf-8").read())
    by_setting: dict[str, list] = defaultdict(list)
    for row in data["rows"]:
        by_setting[row["setting"]].append(row)
    common = _common_words(list(by_setting))
    arms = []
    for setting, rows in by_setting.items():
        scores = [r["score"] for r in rows if r.get("score")]
        arms.append({
            "arm": " ".join(w for w in setting.split() if w not in common) or "(base)",
            "runs": len(rows), "ok": len(scores),
            "ranked": sum(s["ranked"] for s in scores),
            "margin": round(sum(s["marginCents"] for s in scores) / 100),
            "worst": round(min((s["onTimeShare"] for s in scores), default=0), 3),
            "orders": sum(s["wonOrders"] for s in scores),
            "perSeed": {r["seed"]: round(r["score"]["marginCents"] / 100) if r.get("score") else None for r in rows},
        })
    print(f"{data['name']}: {data['seconds']} s, canary {'clean' if data.get('serverClean') else 'NOT CLEAN'}")
    for a in arms:
        print(f"{a['arm'][:58]:<58} ranked {a['ranked']}/{a['runs']}  margin {a['margin']:>8,}  worst {a['worst']:.3f}  orders {a['orders']}")
    return arms


def _common_words(settings: list[str]) -> set:
    sets = [set(s.split()) for s in settings]
    return set.intersection(*sets) if len(sets) > 1 else set()


if __name__ == "__main__":
    for p in sys.argv[1:]:
        table(p)
