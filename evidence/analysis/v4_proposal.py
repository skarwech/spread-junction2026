"""Evidence for the v4 policy proposal (v4_proposal.md). Every number in the report is printed here.

    .venv/bin/python -m evidence.analysis.v4_proposal [cache.pkl] > evidence/analysis/v4_proposal_out.txt

Reads recorded runs only (runs/<world>/{meta,summary}.json, journal.jsonl) and evidence/sweeps/*.json.
No network, no worlds. Runs: the pinned list of governor_parse.RUNS (64 level-8 `priced` runs on dev-1..4 and
hold-1..6, one per identical setting, wc721c95a136b417e5d7c excluded). The optional cache is a pickle of the parse.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from evidence.analysis.governor_parse import open_at
from evidence.analysis.v4_data import ROOT, RunX, load_runs

DAY = 1440
SEEDS = ["dev-1", "dev-2", "dev-3", "dev-4", "hold-1", "hold-2", "hold-3", "hold-4", "hold-5", "hold-6"]
U = "x1.5 deadline"                                  # regime R, no selection
F4 = "x1.5 deadline slack>=4 drive<=5"
F6 = "x1.5 deadline slack>=6 drive<=5"               # current best ("v3")
GATE = 0.90
BRAKE_G = 10                                         # proposed brake_dc
LEVEL_WIN = 0.40                                     # proposed level_win
DAYS = "Mon Tue Wed Thu Fri".split()


def eur(cents: float) -> str:
    return f"{cents / 100:,.0f}"


def quoted(r: RunX, t0: int = 0, t1: int = 10**9) -> list:
    """Requests we really quoted (not a decline at decline_mult x list) with a known outcome, arriving in [t0, t1)."""
    return [q for q in r.reqs.values() if t0 <= q.arrived < t1 and q.quote is not None
            and q.quote < 2 * q.list_first and q.won is not None]


def win_rate(qs: list) -> float:
    return sum(q.won for q in qs) / len(qs) if qs else float("nan")


def spearman(xs: list, ys: list) -> float:
    def ranks(v: list) -> list:
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (sx * sy)


def dc24_series(r: RunX) -> list:
    """(minute, warnings on our orders in the trailing 24 h) at every request arrival."""
    times = sorted(m for m, _ in r.dclose)
    out = []
    for q in sorted(r.reqs.values(), key=lambda q: q.arrived):
        t = q.arrived
        out.append((t, sum(1 for m in times if t - DAY <= m < t)))
    return out


def by(runs: list, seed: str, setting: str) -> RunX | None:
    return next((r for r in runs if r.seed == seed and r.setting == setting), None)


def p1_baseline(runs: list) -> None:
    print("## P1 the three regime-R settings per seed, server score: margin EUR | on-time | won")
    print(f"  {'seed':<7} {'unfiltered':>26} {'slack>=4 drive<=5':>26} {'slack>=6 drive<=5 (v3)':>26}")
    tot = defaultdict(lambda: [0, 0, 1.0, 0])
    for s in SEEDS:
        cells = []
        for st in (U, F4, F6):
            r = by(runs, s, st)
            sc = r.score
            t = tot[st]
            t[0] += sc["marginCents"]
            t[1] += sc["onTimeShare"] >= GATE
            t[2] = min(t[2], sc["onTimeShare"])
            t[3] += sc["marginCents"] if sc["onTimeShare"] >= GATE else 0
            cells.append(f"{eur(sc['marginCents']):>9} | {sc['onTimeShare']:.3f} | {sc['wonOrders']:>3}")
        print(f"  {s:<7} " + "   ".join(f"{c:>24}" for c in cells))
    for st in (U, F4, F6):
        t = tot[st]
        print(f"  {st:<34} total EUR {eur(t[0])}, weeks >= 0.90: {t[1]} of 10, worst {t[2]:.3f}, margin of ranked weeks EUR {eur(t[3])}")


def p2_price(runs: list) -> None:
    print("\n## P2 fixed multipliers, unfiltered, dev seeds: win rate over quoted requests | won | margin EUR | on-time")
    for s in SEEDS[:4]:
        rows = sorted((r for r in runs if r.seed == s and "slack" not in r.setting),
                      key=lambda r: (r.params.get("price_mult", 1.0), r.setting))
        for r in rows:
            sc = r.score
            print(f"  {s} {r.setting:<16} {win_rate(quoted(r)):.2f} | {sc['wonOrders']:>3} | {eur(sc['marginCents']):>8} | {sc['onTimeShare']:.3f}")
    print("  paired (deadline fees): 1.5 vs 1.35 and 1.5 vs 1.65, margin EUR")
    wins135 = wins165 = 0
    for s in SEEDS[:4]:
        m = {pm: by(runs, s, f"x{pm} deadline").score["marginCents"] for pm in ("1.35", "1.5", "1.65")}
        wins135 += m["1.5"] > m["1.35"]
        wins165 += m["1.5"] > m["1.65"]
        print(f"  {s}: 1.35 {eur(m['1.35'])}  1.5 {eur(m['1.5'])}  1.65 {eur(m['1.65'])}")
    print(f"  1.5 beats 1.35 in {wins135} of 4 seeds, beats 1.65 in {wins165} of 4")
    best = []
    for s in SEEDS[:4]:
        rows = [r for r in runs if r.seed == s and "slack" not in r.setting]
        top = max(rows, key=lambda r: r.score["marginCents"])
        best.append((s, top.setting, round(win_rate(quoted(top)), 2), eur(top.score["marginCents"]), top.score["onTimeShare"]))
    print("  best fixed multiplier per dev seed (setting, weekly win rate, margin, on-time):", best)


def p3_level(runs: list) -> None:
    print("\n## P3 world level: weekly win rate over quoted requests at 1.5x (unfiltered run) vs the v3 week")
    xs, ys, zs = [], [], []
    for s in SEEDS:
        u, v = by(runs, s, U), by(runs, s, F6)
        dmax = max(n for _, n in dc24_series(v))
        xs.append(win_rate(quoted(u)))
        ys.append(v.score["onTimeShare"])
        zs.append(dmax)
        print(f"  {s:<7} win rate unfiltered {xs[-1]:.2f}  v3 {win_rate(quoted(v)):.2f} | unfiltered on-time {u.score['onTimeShare']:.3f}"
              f" | v3 on-time {ys[-1]:.3f}, max warnings in 24 h {dmax}")
    print(f"  Spearman(weekly win rate, v3 on-time) = {spearman(xs, ys):+.2f}; Spearman(weekly win rate, v3 max warnings) = {spearman(xs, zs):+.2f}")
    print("  daily win rate over quoted requests, v3 runs (Mon..Fri); * = at or above level_win "
          f"{LEVEL_WIN:.2f}")
    for s in SEEDS:
        v = by(runs, s, F6)
        cells = []
        for d in range(5):
            w = win_rate(quoted(v, d * DAY, (d + 1) * DAY))
            cells.append(f"{w:.2f}{'*' if w >= LEVEL_WIN else ' '}")
        print(f"  {s:<7} " + " ".join(cells))
    print("  lowest daily win rate per v3 week (the price-war day shows as a collapse):",
          {s: min((round(win_rate(quoted(by(runs, s, F6), d * DAY, (d + 1) * DAY)), 2), DAYS[d]) for d in range(5)) for s in SEEDS})
    rates = []
    for s in SEEDS:
        v = by(runs, s, F6)
        rates.append(sum(1 for q in quoted(v) if 9 * 60 <= q.arrived % DAY < 18 * 60) / 45)
    print(f"  quoted (not declined) requests per hour, 09-18 Mon-Fri, v3 runs: min {min(rates):.1f}, max {max(rates):.1f}"
          f" (so a window of 40 answers spans about {40 / max(rates):.1f}-{40 / min(rates):.1f} hours)")


def p4_trust(runs: list) -> None:
    print("\n## P4 dealer trust (RULES.md:163-165), counted from our own ledger")
    bands = [0, 1, 3, 6, 11]
    n = defaultdict(int)
    w = defaultdict(int)
    exp = defaultdict(float)
    for r in runs:
        if not r.setting.startswith("x1.5"):
            continue
        byday = defaultdict(list)
        for q in quoted(r):
            byday[q.arrived // DAY].append(q)
        for qs in byday.values():
            mean = win_rate(qs)
            for q in qs:
                b = max(x for x in bands if x <= q.trust)
                n[b] += 1
                w[b] += q.won
                exp[b] += mean
    print("  all 1.5x runs, quoted requests by the dealer's count at arrival: n | win rate | observed / run-day mean")
    for b in bands:
        print(f"  count >= {b:>2}: {n[b]:>6} | {w[b] / n[b]:.3f} | {w[b] / exp[b]:.2f}")
    print("  v3 runs: mean count of won orders at arrival, revenue-weighted, and the markup's value if wins stay the same")
    total = 0.0
    for s in SEEDS:
        v = by(runs, s, F6)
        won = [(o, v.reqs[o.id].trust) for o in v.orders.values() if o.id in v.reqs]
        rw = sum(o.price * t for o, t in won) / sum(o.price for o, _ in won)
        gain = sum(o.net_rev * 0.01 * t for o, t in won)
        total += gain
        print(f"  {s:<7} mean count {sum(t for _, t in won) / len(won):5.2f}  price-weighted {rw:5.2f}  "
              f"+1%/count on net revenue: EUR {eur(gain)} (v3 margin EUR {eur(v.score['marginCents'])})")
    print(f"  total over 10 v3 weeks: EUR {eur(total)}")
    tops = []
    for s in SEEDS:
        v = by(runs, s, F6)
        c = Counter(q.dealer for q in v.reqs.values() if q.won)
        tops.append(round(c.most_common(1)[0][1] / sum(c.values()), 2))
    print(f"  largest dealer's share of our won orders per v3 week: {tops}")
    print("  check of the count: per v3 week, revenue lines that raised a count / that halved one (late, delivered)"
          " vs late orders that were delivered (late minus undelivered):")
    print("  " + "  ".join(f"{s}: {by(runs, s, F6).trust_up}/{by(runs, s, F6).trust_halved} vs "
                           f"{sum(o.late and not o.undelivered for o in by(runs, s, F6).orders.values())}" for s in SEEDS))


def p5_governor(runs: list) -> None:
    print(f"\n## P5 governor signal: deadline_close warnings on our orders in the trailing 24 h (brake_dc = {BRAKE_G})")
    for s in SEEDS:
        v = by(runs, s, F6)
        series = dc24_series(v)
        dmax = max(x for _, x in series)
        fire = next((t for t, x in series if x >= BRAKE_G), None)
        orders = list(v.orders.values())
        after = [o for o in orders if fire is not None and o.arrived >= fire]
        before = [o for o in orders if fire is None or o.arrived < fire]
        late_b = sum(o.late for o in before)
        late_a = sum(o.late for o in after)
        when = f"{DAYS[fire // DAY]} {fire % DAY // 60:02d}:{fire % 60:02d}" if fire is not None and fire // DAY < 5 else "never"
        share = f"{after.__len__()} orders after, {late_a} late ({late_a / len(after):.2f})" if after else "-"
        print(f"  {s:<7} v3 on-time {v.score['onTimeShare']:.3f} max {dmax:>2} first >= {BRAKE_G}: {when:<10} | before: {len(before)} orders, "
              f"{late_b} late ({late_b / len(before):.2f}) | after: {share}")
    print("  late share of v3-regime orders by warnings in the 24 h before arrival (all 1.5x deadline runs):")
    pool = defaultdict(lambda: [0, 0])
    for r in runs:
        if not r.setting.startswith("x1.5 deadline"):
            continue
        times = sorted(m for m, _ in r.dclose)
        for o in r.orders.values():
            k = sum(1 for m in times if o.arrived - DAY <= m < o.arrived)
            b = max(x for x in (0, 1, 5, 10, 20) if x <= k)
            pool[b][0] += 1
            pool[b][1] += o.late
    print("  " + "  ".join(f">={b}: {pool[b][0]} orders, late {pool[b][1] / pool[b][0]:.3f}" for b in sorted(pool)))
    print("  state-blind replay of the v3 weeks (drop orders that arrived while the signal was on; keep every other"
          " outcome). It cannot show the drivers a governor frees, so it is shown only as a floor:")
    for g in (5, 10, 20):
        res = []
        for s in SEEDS:
            v = by(runs, s, F6)
            kept, ids = [], set()
            times = sorted(v.dclose)
            for o in sorted(v.orders.values(), key=lambda o: o.arrived):
                k = sum(1 for m, oid in times if o.arrived - DAY <= m < o.arrived and oid in ids)
                if k < g:
                    kept.append(o)
                    ids.add(o.id)
            res.append(1 - sum(o.late for o in kept) / len(kept))
        print(f"  brake_dc {g:>2} (decline while on): weeks >= 0.90 {sum(x >= GATE for x in res)} of 10, worst {min(res):.3f}")
    print("  open orders at arrival vs lateness (all 1.5x deadline runs): open-order band | orders | late share")
    pool = defaultdict(lambda: [0, 0])
    for r in runs:
        if not r.setting.startswith("x1.5 deadline"):
            continue
        orders = list(r.orders.values())
        for o in orders:
            k = sum(1 for x in orders if x.id != o.id and open_at(x, o.arrived))
            b = max(x for x in (0, 20, 40, 60, 80, 100, 130) if x <= k)
            pool[b][0] += 1
            pool[b][1] += o.late
    print("  " + "  ".join(f">={b}: {pool[b][0]} {pool[b][1] / pool[b][0]:.3f}" for b in sorted(pool)))


def p6_fees(runs: list) -> None:
    print("\n## P6 fees")
    print("  starter vs deadline fees, same seed and multiplier (unfiltered): margin EUR | on-time")
    better_m = better_t = 0
    deltas = []
    for s in SEEDS[:4]:
        for pm in ("1.35", "1.5", "1.65"):
            a, b = by(runs, s, f"x{pm} starter"), by(runs, s, f"x{pm} deadline")
            dm = b.score["marginCents"] - a.score["marginCents"]
            dt = b.score["onTimeShare"] - a.score["onTimeShare"]
            deltas.append(dm)
            better_m += dm > 0
            better_t += dt > 0
            print(f"  {s} x{pm:<4}: starter {eur(a.score['marginCents']):>8} | {a.score['onTimeShare']:.3f}   "
                  f"deadline {eur(b.score['marginCents']):>8} | {b.score['onTimeShare']:.3f}   delta EUR {eur(dm):>6}, on-time {dt:+.3f}")
    deltas.sort()
    print(f"  deadline better on margin in {better_m} of 12 pairs, on on-time in {better_t} of 12; "
          f"mean delta EUR {eur(sum(deltas) / 12)}, median EUR {eur((deltas[5] + deltas[6]) / 2)}")
    print("  v3 runs: bookings | share booked at the schedule's opening fee | share under the post-warning steep schedule"
          " | booked fee / typical fee p50, p90 | driver+release fees / revenue")
    for s in SEEDS:
        v = by(runs, s, F6)
        b = v.bookings
        ratios = sorted(x.fee / x.ref for x in b if x.ref)
        print(f"  {s:<7} {len(b):>4} | {sum(x.fee == x.opening for x in b) / len(b):.2f} | {sum(x.urgent for x in b) / len(b):.2f} | "
              f"{ratios[len(ratios) // 2]:.2f}, {ratios[int(0.9 * len(ratios))]:.2f} | {v.fee_cents / v.revenue_cents:.2f}")
    causes = Counter()
    sweeps = ROOT / "evidence" / "sweeps"
    for name in ("select1", "holdout1"):
        for row in json.loads((sweeps / f"{name}.json").read_text())["rows"]:
            if row["setting"].endswith("min_slack_h=6 max_drive_h=5") and "diag" in row:
                causes.update(row["diag"]["lateCauses"])
    print(f"  late causes over the 10 v3 weeks (tools.diagnose in the sweep files): {dict(causes.most_common())}")


def p7_decline(runs: list) -> None:
    n = won = 0
    for r in runs:
        for q in r.reqs.values():
            if q.quote is not None and q.quote >= 3 * q.list_first:
                n += 1
                won += bool(q.won)
    print(f"\n## P7 decline_mult = 4: declined quotes (>= 3x list) in all 64 runs: {n}, won: {won}")


def p8_check(runs: list) -> None:
    print("\n## P8 cross-check of risk.md figures used here")
    v3 = [by(runs, s, F6) for s in SEEDS]
    srv = sum(r.score["marginCents"] for r in v3)
    per = sum(sum(o.pnl for o in r.orders.values()) for r in v3)
    print(f"  v3 played over 10 weeks: server margin EUR {eur(srv)}, per-order P&L sum EUR {eur(per)} (risk.md quotes the latter, 60,490)")


def main() -> None:
    cache = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    runs = load_runs(cache)
    print(f"# v4 proposal evidence: {len(runs)} pinned runs\n")
    p1_baseline(runs)
    p2_price(runs)
    p3_level(runs)
    p4_trust(runs)
    p5_governor(runs)
    p6_fees(runs)
    p7_decline(runs)
    p8_check(runs)


if __name__ == "__main__":
    main()
