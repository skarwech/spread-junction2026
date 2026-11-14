"""Lateness risk at quote time: P(late) of a won order, from what the desk knows when the request arrives.

Read-only: runs/<worldId>/{meta,summary}.json, journal.jsonl and data/map.json. No network, no worlds.
Prints every number quoted in risk.md, section by section (S1 ... S10):

    .venv/bin/python -m evidence.analysis.risk > evidence/analysis/risk_out.txt

Data: won orders of the L8 `priced` runs. Dev seeds dev-1..dev-4 (risk_data.PINNED, deduplicated) are used for
fitting and leave-one-seed-out validation; seeds hold-1..hold-6 (HOLD_PINNED) are never fitted on and serve as
an external check. Labels: late = a late_refund or undelivered_penalty ledger line (risk_data.run_rows).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean, pstdev
from typing import Callable, Iterable

from evidence.analysis.risk_data import load_rows
from evidence.analysis.risk_model import auc, brier, calibration_line, fit_logit, logit, logloss

DEV = ("dev-1", "dev-2", "dev-3", "dev-4")
HOLD = ("hold-1", "hold-2", "hold-3", "hold-4", "hold-5", "hold-6")
# every L8 `priced` run on hold-1..hold-6 with a summary.json at analysis time (14 Nov): sweep holdout1
HOLD_PINNED = [
    "w02aa24a2ae3cacf98273", "w052ee407759a6feff382", "w1e3bbbe2181bbab6b71e", "w2be6bf3133a7eb751f8e",
    "w3141bd32f5c368ffb841", "w3330bb6305399cfce674", "w54f8eed3566b8f8d5c0c", "w65b39bae2860de2bcb23",
    "w879a3d155f64e646d7d1", "w8ca4f470083e84b2e71e", "w9092eceae0d66c1c9230", "wa0067bc996bb1b5b865b",
    "wb1fd6f568123c7c17f54", "wb9035c91670e517859d1", "wbd2ee97d7536a679a5d8", "wc69e73feb96e6f9072b2",
    "wf275f9c05bf437789405", "wf94c3a185b7c7edacfe3",
]
SLACK_EDGES = (2, 4, 6, 8, 12, 24, 36)
DAY_EDGES = (2, 4, 6, 8, 10)
ONLINE_PRIOR_N, ONLINE_PRIOR_P, TOWN_PRIOR_N = 10, 0.15, 5
PLACE_PRIOR_N = 50
THRESHOLDS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 1.01)
GATE = 0.10
EUR = 100.0


# ---------------------------------------------------------------- data

def in_regime(r: dict) -> bool:
    """The candidate regime: price_mult 1.5 with deadline fees (fees1, select1 and holdout1 all play it)."""
    return r["price_mult"] == 1.5 and r["fee_mode"] == "deadline"


def unfiltered(r: dict) -> bool:
    return r["min_slack_h"] < -100 and r["max_drive_h"] > 100


def with_online(rows: list[dict]) -> list[dict]:
    """Adds what the desk has seen of its own lateness by the request's arrival: the late share of its orders
    whose deadline has passed (all of them, and those from the same pickup town), shrunk to a prior."""
    by_world = defaultdict(list)
    for r in rows:
        by_world[r["world"]].append(r)
    out = []
    for rs in by_world.values():
        for r in rs:
            t = r["arrived"]
            matured = [o for o in rs if o["order_deadline"] < t]
            run_rate = (sum(o["late"] for o in matured) + ONLINE_PRIOR_N * ONLINE_PRIOR_P) / (len(matured) + ONLINE_PRIOR_N)
            town = [o for o in matured if o["pickup"] == r["pickup"]]
            town_rate = (sum(o["late"] for o in town) + TOWN_PRIOR_N * run_rate) / (len(town) + TOWN_PRIOR_N)
            out.append({**r, "run_late_sofar": run_rate, "town_late_sofar": town_rate, "matured": len(matured)})
    return out


def load(world_ids: list[str] | None) -> tuple[list[dict], dict]:
    rows, info = load_rows(world_ids)
    unresolved = [r for r in rows if not r["resolved"]]
    odd_kind = [r for r in rows if r["kind"] == "within_3_days"]
    keep = [r for r in rows if r["resolved"] and r["kind"] != "within_3_days"]
    return with_online(keep), {**info, "unresolved": len(unresolved), "unresolved_runs": Counter(r["world"] for r in unresolved),
                               "within_3_days": len(odd_kind)}


# ---------------------------------------------------------------- features

def band(x: float, edges: Iterable[float]) -> tuple[int, str]:
    edges = list(edges)
    for i, e in enumerate(edges):
        if x < e:
            return i, f"<{e:g}" if i == 0 else f"{edges[i - 1]:g}-{e:g}"
    return len(edges), f">={edges[-1]:g}"


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
Feat = Callable[[dict, dict], list[tuple[str, float]]]


def g_slack(r: dict, _: dict) -> list[tuple[str, float]]:
    i, _lab = band(r["slack_h"], SLACK_EDGES)
    labels = [band(e - 0.01, SLACK_EDGES)[1] for e in SLACK_EDGES] + [f">={SLACK_EDGES[-1]}"]
    return [(f"slack {lab}", float(i == k)) for k, lab in enumerate(labels) if lab != "8-12"]


def g_day(r: dict, _: dict) -> list[tuple[str, float]]:
    s = r["best_day_slack_h"]
    return [("best-day slack short of 10h (h)", max(0.0, 10 - s)), ("... short of 4h (h)", max(0.0, 4 - s))]


GROUPS: dict[str, Feat] = {
    "slack": g_slack,
    "dayslack": g_day,
    "day10": lambda r, _: [("best-day slack short of 10h (h)", max(0.0, 10 - r["best_day_slack_h"]))],
    "drive": lambda r, _: [("drive h", min(r["drive_h"], 10.0))],
    "kind": lambda r, _: [("same_day", float(r["kind"] == "same_day"))],
    "legs": lambda r, _: [("two legs", float(r["legs"] == 2))],
    "private": lambda r, _: [("private pickup", float(r["priv_pickup"])), ("private delivery", float(r["priv_delivery"]))],
    "premium": lambda r, _: [("premium", float(r["premium"]))],
    "ev_low": lambda r, _: [("EV <30%", float(r["ev_low"]))],
    "note": lambda r, _: [("note", float(r["note"]))],
    "weekday": lambda r, _: [(d, float(r["weekday"] == i)) for i, d in enumerate(WEEKDAYS) if i],
    "hour": lambda r, _: [("arrival hour", r["hour"])],
    "policy": lambda r, _: [("price_mult", r["price_mult"]), ("deadline fees", float(r["fee_mode"] == "deadline"))],
    "book": lambda r, _: [("log(1+open orders)", math.log1p(r["book"]))],
    "places": lambda r, c: [("pickup town code", c["pickup"].get(r["pickup"], 0.0)),
                            ("delivery town code", c["delivery"].get(r["delivery"], 0.0))],
    "online": lambda r, _: [("logit late share so far", logit(r["run_late_sofar"])),
                            ("logit town late share so far", logit(r["town_late_sofar"]) - logit(r["run_late_sofar"]))],
}
REQUEST = ["drive", "kind", "legs", "private", "premium", "ev_low", "note", "weekday", "hour"]
CONTEXT = ["policy", "book"]
MODELS = {
    "A slack only": ["slack"] + CONTEXT,
    "B task features": ["slack"] + REQUEST + CONTEXT,
    "B' best-day slack": ["dayslack"] + REQUEST + CONTEXT,
    "C B + places": ["slack"] + REQUEST + CONTEXT + ["places"],
    "D B + online": ["slack"] + REQUEST + CONTEXT + ["online"],
    "E B' + online": ["dayslack"] + REQUEST + CONTEXT + ["online"],
    # chosen after S7 (drop-one on B and E): only the groups that helped out of seed. Its LOSO numbers are
    # therefore slightly optimistic; its hold-seed numbers (S11) are not.
    # variants compared on LOSO only (one 10 h hinge; +drive, +note, +kind, +EV): +drive+note had the best LOSO
    # log-loss (0.3715) at equal within-run AUC (0.783).
    "F compact": ["day10", "drive", "legs", "private", "premium", "note", "book", "online"],
}
CHOSEN = "F compact"


def place_codes(rows: list[dict]) -> dict:
    """Town log-odds relative to the rows' base rate, shrunk with PLACE_PRIOR_N pseudo-orders."""
    base = mean(r["late"] for r in rows)
    out = {}
    for side in ("pickup", "delivery"):
        n, k = Counter(r[side] for r in rows), Counter(r[side] for r in rows if r["late"])
        out[side] = {t: logit((k[t] + PLACE_PRIOR_N * base) / (n[t] + PLACE_PRIOR_N)) - logit(base) for t in n}
    return out


def design(rows: list[dict], groups: list[str], codes: Callable[[dict], dict]) -> tuple[list[str], list[list[float]]]:
    names: list[str] = []
    xs = []
    for r in rows:
        feats = [f for g in groups for f in GROUPS[g](r, codes(r))]
        if not names:
            names = [n for n, _ in feats]
        xs.append([v for _, v in feats])
    return names, xs


def fit_predict(train: list[dict], test: list[dict], groups: list[str]):
    """Fits on train, predicts test. Place codes of a training row come from the other training seeds only."""
    seeds = sorted({r["seed"] for r in train})
    if "places" in groups:
        own = {s: place_codes([r for r in train if r["seed"] != s]) for s in seeds}
        full = place_codes(train)
        c_train, c_test = (lambda r: own[r["seed"]]), (lambda r: full)
    else:
        c_train = c_test = (lambda r: {})
    names, xs = design(train, groups, c_train)
    model = fit_logit(names, xs, [int(r["late"]) for r in train])
    _, xt = design(test, groups, c_test)
    return model, [model.prob(x) for x in xt]


# ---------------------------------------------------------------- metrics

def within_run_auc(rows: list[dict], ps: list[float]) -> float:
    by = defaultdict(lambda: ([], []))
    for r, p in zip(rows, ps):
        by[r["world"]][0].append(p)
        by[r["world"]][1].append(int(r["late"]))
    vals = [auc(s, y) for s, y in by.values() if 0 < sum(y) < len(y)]
    return mean(vals) if vals else float("nan")


def metrics(rows: list[dict], ps: list[float]) -> dict:
    ys = [int(r["late"]) for r in rows]
    const = max(ps) - min(ps) < 1e-12
    a, b = (float("nan"), float("nan")) if const or not 0 < sum(ys) < len(ys) else calibration_line(ps, ys)
    return {"n": len(ys), "obs": mean(ys), "pred": mean(ps), "auc": float("nan") if const else auc(ps, ys),
            "auc_run": float("nan") if const else within_run_auc(rows, ps), "cal_a": a, "cal_b": b,
            "brier": brier(ps, ys), "logloss": logloss(ps, ys)}


def fmt(m: dict) -> str:
    return (f"n={m['n']:5d} obs={m['obs']:.3f} pred={m['pred']:.3f} AUC={m['auc']:.3f} AUC_in_run={m['auc_run']:.3f} "
            f"cal_int={m['cal_a']:+.2f} cal_slope={m['cal_b']:.2f} brier={m['brier']:.4f} logloss={m['logloss']:.4f}")


def loso(rows: list[dict], groups: list[str] | None) -> dict[str, list[float]]:
    """Out-of-fold predictions, one fold per dev seed. groups None: the training base rate."""
    oof = {}
    for s in DEV:
        train, test = [r for r in rows if r["seed"] != s], [r for r in rows if r["seed"] == s]
        if groups is None:
            base = mean(r["late"] for r in train)
            oof[s] = [base] * len(test)
        else:
            oof[s] = fit_predict(train, test, groups)[1]
    return oof


def spearman(a: list[float], b: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        for rank, i in enumerate(order):
            out[i] = float(rank)
        return out
    ra, rb = ranks(a), ranks(b)
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    return num / math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))


# ---------------------------------------------------------------- sections

def s1_data(dev: list[dict], hold: list[dict], dinfo: dict, hinfo: dict) -> None:
    print("\n## S1 data")
    for name, rows, info in (("dev", dev, dinfo), ("hold", hold, hinfo)):
        print(f"{name}: runs kept {len(info['kept'])}, duplicates dropped {len(info['duplicates'])}, "
              f"unresolved orders dropped {info['unresolved']} {dict(info['unresolved_runs'])}, within_3_days dropped {info['within_3_days']}")
        print(f"{name}: orders {len(rows)}, late {sum(r['late'] for r in rows)} ({mean(r['late'] for r in rows):.3f}), "
              f"undelivered {sum(r['undelivered'] for r in rows)}")
        for s in sorted({r["seed"] for r in rows}):
            rs = [r for r in rows if r["seed"] == s]
            rr = [r for r in rs if in_regime(r)]
            ru = [r for r in rr if unfiltered(r)]
            print(f"  {s}: runs {len({r['world'] for r in rs})} orders {len(rs)} late {mean(r['late'] for r in rs):.3f} | "
                  f"regime R runs {len({r['world'] for r in rr})} orders {len(rr)} late {mean(r['late'] for r in rr) if rr else float('nan'):.3f} | "
                  f"R unfiltered orders {len(ru)} late {mean(r['late'] for r in ru) if ru else float('nan'):.3f}")


def s1c_label_check(rows: list[dict]) -> None:
    """Our late labels against the server's final onTimeShare (summary.json, last day)."""
    import json
    from evidence.analysis.risk_data import ROOT
    by = defaultdict(list)
    for r in rows:
        by[r["world"]].append(r)
    diffs, mdiffs = [], []
    for w, rs in by.items():
        days = json.loads((ROOT / "runs" / w / "summary.json").read_text())["days"]
        diffs.append(abs(days[-1]["score"]["onTimeShare"] - (1 - mean(r["late"] for r in rs))))
        mdiffs.append((sum(r["margin"] for r in rs) - days[-1]["score"]["marginCents"]) / EUR)
    print(f"\n## S1c label check: on-time share from our labels equals the server's in {sum(d < 1e-9 for d in diffs)} of "
          f"{len(diffs)} runs; max abs difference {max(diffs):.4f}")
    print(f"  per-order margin sum minus server margin, EUR: mean {mean(mdiffs):+.0f}, median {sorted(mdiffs)[len(mdiffs) // 2]:+.0f}, "
          f"min {min(mdiffs):+.0f}, max {max(mdiffs):+.0f} (lines not attributable to a kept order: unmatched gigs, dropped orders)")


def s1b_win_vs_price(dev: list[dict]) -> None:
    print("\n## S1b won orders by price_mult, unfiltered runs, per seed and fee mode")
    cells = defaultdict(set)
    count = Counter()
    for r in dev:
        if unfiltered(r):
            cells[(r["seed"], r["fee_mode"], r["price_mult"])].add(r["world"])
            count[r["world"]] += 1
    for k in sorted(cells):
        print(f"  {k[0]} {k[1]:>8} x{k[2]:.2f}: " + ", ".join(f"{count[w]}" for w in sorted(cells[k])))


def s2_univariate(dev: list[dict]) -> None:
    print("\n## S2 late share by feature level (dev). cols: level | n all | late all | n R | late R | late per seed dev-1..4 (all regimes)")
    levels = [
        ("slack h (task def.)", lambda r: band(r["slack_h"], SLACK_EDGES)),
        ("best-day slack h", lambda r: band(r["best_day_slack_h"], DAY_EDGES)),
        ("drive h", lambda r: band(r["drive_h"], (1, 2, 3, 4, 5, 6, 8))),
        ("kind", lambda r: (0, r["kind"])),
        ("kind x slack", lambda r: (0, r["kind"] + " " + band(r["slack_h"], SLACK_EDGES)[1])),
        ("weekday", lambda r: (r["weekday"], WEEKDAYS[r["weekday"]])),
        ("arrival hour", lambda r: band(r["hour"], (10, 12, 14, 16))),
        ("legs", lambda r: (r["legs"], str(r["legs"]))),
        ("private pickup", lambda r: (0, str(r["priv_pickup"]))),
        ("private delivery", lambda r: (0, str(r["priv_delivery"]))),
        ("premium", lambda r: (0, str(r["premium"]))),
        ("EV <30%", lambda r: (0, str(r["ev_low"]))),
        ("EV <30% on >200 km", lambda r: (0, str(r["ev_low_long"]))),
        ("note", lambda r: (0, str(r["note"]))),
        ("open orders at arrival", lambda r: band(r["book"], (20, 40, 80, 160))),
        ("late share so far", lambda r: band(r["run_late_sofar"], (0.1, 0.2, 0.3))),
    ]
    for name, key in levels:
        print(f"- {name}")
        cells = defaultdict(list)
        for r in dev:
            cells[key(r)].append(r)
        for k in sorted(cells):
            rs = cells[k]
            rr = [r for r in rs if in_regime(r)]
            per = " ".join(f"{mean(r['late'] for r in rs if r['seed'] == s):.2f}" if any(r["seed"] == s for r in rs) else "  - " for s in DEV)
            print(f"  {k[1]:>22} | {len(rs):5d} | {mean(r['late'] for r in rs):.3f} | {len(rr):4d} | "
                  f"{mean(r['late'] for r in rr) if rr else float('nan'):.3f} | {per}")


def s3_places(dev: list[dict]) -> None:
    print("\n## S3 do town late shares carry over between seeds? Spearman of town late share, towns with >=40 orders in both seeds")
    for side in ("pickup", "delivery"):
        rates = {}
        for s in DEV:
            n, k = Counter(), Counter()
            for r in dev:
                if r["seed"] == s:
                    n[r[side]] += 1
                    k[r[side]] += r["late"]
            rates[s] = {t: (k[t] / n[t], n[t]) for t in n}
        pairs = []
        for i, a in enumerate(DEV):
            for b in DEV[i + 1:]:
                towns = [t for t in rates[a] if t in rates[b] and rates[a][t][1] >= 40 and rates[b][t][1] >= 40]
                if len(towns) >= 5:
                    rho = spearman([rates[a][t][0] for t in towns], [rates[b][t][0] for t in towns])
                    pairs.append(rho)
                    print(f"  {side} {a} vs {b}: towns {len(towns)} rho {rho:+.2f}")
        print(f"  {side}: mean rho {mean(pairs):+.2f} over {len(pairs)} seed pairs")


def s4_loso(dev: list[dict]) -> dict[str, dict[str, list[float]]]:
    print("\n## S4 leave-one-seed-out (fit on 3 dev seeds, test on the 4th). Per held-out seed: all its runs, then regime R only")
    all_oof = {"M0 base rate": loso(dev, None)}
    for name, groups in MODELS.items():
        all_oof[name] = loso(dev, groups)
    for name, oof in all_oof.items():
        print(f"- {name}")
        pooled_rows, pooled_ps = [], []
        for s in DEV:
            rows = [r for r in dev if r["seed"] == s]
            ps = oof[s]
            pooled_rows += rows
            pooled_ps += ps
            rr = [(r, p) for r, p in zip(rows, ps) if in_regime(r)]
            print(f"  {s} all: {fmt(metrics(rows, ps))}")
            print(f"  {s}   R: {fmt(metrics([r for r, _ in rr], [p for _, p in rr]))}")
        m = metrics(pooled_rows, pooled_ps)
        print(f"  pooled out-of-fold: {fmt(m)}")
        aucs = [metrics([r for r in dev if r['seed'] == s], all_oof[name][s])["auc_run"] for s in DEV]
        print(f"  mean over seeds of within-run AUC: {mean(aucs):.3f} (min {min(aucs):.3f})")
    return all_oof


def oof_rows(dev: list[dict], oof: dict[str, list[float]]) -> list[tuple[dict, float]]:
    return [(r, p) for s in DEV for r, p in zip([r for r in dev if r["seed"] == s], oof[s])]


def s5_calibration(pairs: list[tuple[dict, float]], label: str) -> None:
    print(f"\n## S5 calibration bins, {label}: bin | n | mean predicted | observed | per seed observed/predicted")
    edges = (0, 0.05, 0.10, 0.20, 0.30, 0.50, 1.01)
    for lo, hi in zip(edges, edges[1:]):
        sel = [(r, p) for r, p in pairs if lo <= p < hi]
        if not sel:
            continue
        per = []
        for s in sorted({r["seed"] for r, _ in pairs}):
            ss = [(r, p) for r, p in sel if r["seed"] == s]
            per.append(f"{s}:{mean(r['late'] for r, _ in ss):.2f}/{mean(p for _, p in ss):.2f}({len(ss)})" if ss else f"{s}:-")
        print(f"  {lo:.2f}-{min(hi, 1):.2f} | {len(sel):5d} | {mean(p for _, p in sel):.3f} | {mean(r['late'] for r, _ in sel):.3f} | {' '.join(per)}")


def s6_coefficients(dev: list[dict], name: str) -> None:
    groups = MODELS[name]
    print(f"\n## S6 coefficients of {name}, fitted on all dev rows: log-odds per unit, odds ratio, and sign in the 4 LOSO fits")
    full, _ = fit_predict(dev, dev[:1], groups)
    folds = [fit_predict([r for r in dev if r["seed"] != s], dev[:1], groups)[0] for s in DEV]
    print(f"  intercept (raw units) {full.raw_intercept():+.3f}")
    for i, (n, b) in enumerate(full.per_unit()):
        signs = "".join("+" if f.per_unit()[i][1] > 0 else "-" for f in folds)
        lo, hi = min(f.per_unit()[i][1] for f in folds), max(f.per_unit()[i][1] for f in folds)
        print(f"  {n:>34}: {b:+.3f}  OR {math.exp(b):5.2f}  folds {signs}  range [{lo:+.3f}, {hi:+.3f}]  "
              f"(sd of feature {full.sd[i]:.2f})")


def s7_drop_one(dev: list[dict], name: str) -> None:
    groups = MODELS[name]
    print(f"\n## S7 drop one group from {name}: change in LOSO metrics (negative AUC change = the group helps)")
    base = loso(dev, groups)
    bp = oof_rows(dev, base)
    b_auc = mean(within_run_auc([r for r in dev if r["seed"] == s], base[s]) for s in DEV)
    b_ll = logloss([p for _, p in bp], [int(r["late"]) for r, _ in bp])
    print(f"  full: mean within-run AUC {b_auc:.4f}, pooled logloss {b_ll:.4f}")
    for g in groups:
        oof = loso(dev, [x for x in groups if x != g])
        pp = oof_rows(dev, oof)
        a = mean(within_run_auc([r for r in dev if r["seed"] == s], oof[s]) for s in DEV)
        per_seed = " ".join(f"{within_run_auc([r for r in dev if r['seed'] == s], oof[s]) - within_run_auc([r for r in dev if r['seed'] == s], base[s]):+.4f}" for s in DEV)
        ll = logloss([p for _, p in pp], [int(r["late"]) for r, _ in pp])
        print(f"  without {g:>8}: dAUC_in_run {a - b_auc:+.4f} (per seed {per_seed})  dlogloss {ll - b_ll:+.4f}")


def s8_severity(dev: list[dict], hold: list[dict]) -> float:
    print("\n## S8 severity: refund share of price among late orders (undelivered = 3: no price, 2x penalty)")

    def tier(r: dict) -> str:
        s = r["loss_share"]
        return "undelivered" if r["undelivered"] else "10%" if s < 0.2 else "25%" if s < 0.4 else "50%" if s < 0.75 else "100%"

    out = float("nan")
    for label, rows in (("dev all", dev), ("dev R", [r for r in dev if in_regime(r)]), ("hold R", hold)):
        late = [r for r in rows if r["late"]]
        c = Counter(tier(r) for r in late)
        sev = mean(r["loss_share"] for r in late)
        print(f"  {label}: late {len(late)} tiers " + " ".join(f"{t}:{c[t] / len(late):.2f}" for t in ("10%", "25%", "50%", "100%", "undelivered"))
              + f"  E[share|late] {sev:.3f}  mean price EUR {mean(r['price'] for r in rows) / EUR:.1f}")
        if label == "dev R":
            out = sev
    rr = [r for r in dev + hold if in_regime(r) and r["late"]]
    print("  E[share|late] by task slack band, regime R dev+hold:")
    cells = defaultdict(list)
    for r in rr:
        cells[band(r["slack_h"], SLACK_EDGES)].append(r["loss_share"])
    for k in sorted(cells):
        print(f"    {k[1]:>6}: n {len(cells[k]):4d}  E[share|late] {mean(cells[k]):.3f}")
    cells = defaultdict(list)
    for r in rr:
        cells[r["kind"]].append(r["loss_share"])
    print("  by kind: " + "  ".join(f"{k} {mean(v):.3f} (n {len(v)})" for k, v in sorted(cells.items())))
    return out


def s9_economics(pairs: list[tuple[dict, float]], sev: float) -> None:
    print("\n## S9 regime R, out-of-fold P(late) bands: realized margin per order and expected lateness cost")
    edges = (0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.01)
    for lo, hi in zip(edges, edges[1:]):
        sel = [(r, p) for r, p in pairs if lo <= p < hi]
        if not sel:
            continue
        price = mean(r["price"] for r, _ in sel) / EUR
        print(f"  p {lo:.2f}-{min(hi, 1):.2f}: n {len(sel):5d}  late {mean(r['late'] for r, _ in sel):.3f}  "
              f"price EUR {price:6.1f}  margin/order EUR {mean(r['margin'] for r, _ in sel) / EUR:+7.1f}  "
              f"of which refunds+penalty EUR {-mean(r['refund'] + r['penalty'] for r, _ in sel) / EUR:+6.1f}  "
              f"model refund cost p*S*price EUR {mean(p for _, p in sel) * sev * price:5.1f}")


def decline_table(runs: dict[str, list[tuple[dict, float]]], label: str) -> None:
    print(f"\n## S10 offline decline sweep, {label}: drop won orders with P(late) > p*; on-time share of the rest | margin EUR of the rest")
    head = "  run (seed)                     " + " ".join(f"p*={t:<4.2f}".replace("p*=1.01", "  keep all") for t in THRESHOLDS)
    print(head)
    for w, pairs in sorted(runs.items(), key=lambda kv: kv[1][0][0]["seed"]):
        cells = []
        for t in THRESHOLDS:
            kept = [r for r, p in pairs if p <= t]
            share = 1 - mean(r["late"] for r in kept) if kept else float("nan")
            cells.append(f"{share:.3f}|{sum(r['margin'] for r in kept) / EUR:7.0f}|{len(kept):3d}")
        print(f"  {w} ({pairs[0][0]['seed']}) " + " ".join(cells))


def rule_check(runs_all: list[dict], pred: dict[str, list[tuple[dict, float]]]) -> None:
    print("\n## S10b offline drop vs the real filtered runs (same seed). Rule slack<a or drive>5 applied to the unfiltered run, vs the run that played it")
    by_seed = defaultdict(dict)
    for r in runs_all:
        if in_regime(r):
            by_seed[r["seed"]].setdefault((r["min_slack_h"], r["max_drive_h"]), set()).add(r["world"])
    rows_by_world = defaultdict(list)
    for r in runs_all:
        rows_by_world[r["world"]].append(r)
    gaps: list[tuple[float, float]] = []
    for s in sorted(by_seed):
        base = by_seed[s].get((-999.0, 999.0))
        if not base:
            continue
        bw = sorted(base)[0]
        for (a, d), ws in sorted(by_seed[s].items()):
            if a < -100:
                continue
            real = rows_by_world[sorted(ws)[0]]
            kept = [r for r in rows_by_world[bw] if r["slack_h"] >= a and r["drive_h"] <= d]
            pk = [(r, p) for r, p in pred.get(bw, []) if r["slack_h"] >= a and r["drive_h"] <= d]
            real_ot, off_ot = 1 - mean(r["late"] for r in real), 1 - mean(r["late"] for r in kept)
            gaps.append((real_ot - off_ot, (sum(r["margin"] for r in real) - sum(r["margin"] for r in kept)) / EUR))
            print(f"  {s} min_slack {a:g} max_drive {d:g}: real run on-time {real_ot:.3f} won {len(real)} "
                  f"margin EUR {sum(r['margin'] for r in real) / EUR:.0f} | offline drop from unfiltered: on-time "
                  f"{off_ot:.3f} kept {len(kept)} margin EUR {sum(r['margin'] for r in kept) / EUR:.0f}"
                  + (f" | model expected on-time of kept {1 - mean(p for _, p in pk):.3f}" if pk else ""))
    on = sorted(g for g, _ in gaps)
    print(f"  real minus offline on-time over {len(gaps)} pairs: mean {mean(on):+.3f} median {on[len(on) // 2]:+.3f} "
          f"min {on[0]:+.3f} max {on[-1]:+.3f}; real minus offline margin EUR mean {mean(m for _, m in gaps):+.0f}")


def s10c_compare(runs: dict[str, list[tuple[dict, float]]], p_star: float) -> None:
    print(f"\n## S10c offline drop, unfiltered R runs (dev LOSO + hold): P(late) > {p_star} vs the slack/drive filters")
    rules = {f"P>{p_star}": lambda r, p: p <= p_star,
             "slack<6|drive>5": lambda r, p: r["slack_h"] >= 6 and r["drive_h"] <= 5,
             "slack<4|drive>5": lambda r, p: r["slack_h"] >= 4 and r["drive_h"] <= 5}
    tot = Counter()
    worst = {}
    for w, pairs in sorted(runs.items(), key=lambda kv: kv[1][0][0]["seed"]):
        cells = []
        for name, keep in rules.items():
            kept = [r for r, p in pairs if keep(r, p)]
            ot, m = 1 - mean(r["late"] for r in kept), sum(r["margin"] for r in kept) / EUR
            tot[name] += m
            tot[name + " ranked"] += ot >= 1 - GATE
            worst[name] = min(worst.get(name, 1.0), ot)
            cells.append(f"{name}: {ot:.3f}|{m:6.0f}|{len(kept):3d}")
        print(f"  {w} ({pairs[0][0]['seed']}) " + "   ".join(cells))
    for name in rules:
        print(f"  {name}: total margin EUR {tot[name]:.0f}, runs >= 0.90 on time {tot[name + ' ranked']} of {len(runs)}, worst on-time {worst[name]:.3f}")


def s10c_real(all_rows: list[dict]) -> None:
    """The filters as actually played (select1 and holdout1 runs), on the same weeks."""
    import json
    from evidence.analysis.risk_data import ROOT
    print("\n## S10c-real the slack/drive filters as actually played: on-time | margin EUR (per-order sum) | server margin EUR")
    by = defaultdict(list)
    for r in all_rows:
        if in_regime(r) and r["max_drive_h"] == 5.0:
            by[(r["min_slack_h"], r["seed"], r["world"])].append(r)
    for a in (6.0, 4.0):
        tot, srv, ok, worst, n = 0.0, 0.0, 0, 1.0, 0
        for (aa, seed, w), rs in sorted(by.items()):
            if aa != a:
                continue
            ot = 1 - mean(r["late"] for r in rs)
            m = sum(r["margin"] for r in rs) / EUR
            sm = json.loads((ROOT / "runs" / w / "summary.json").read_text())["days"][-1]["score"]["marginCents"] / EUR
            tot, srv, ok, worst, n = tot + m, srv + sm, ok + (ot >= 1 - GATE), min(worst, ot), n + 1
            print(f"  slack<{a:g}|drive>5 {seed} {w}: {ot:.3f} | {m:.0f} | {sm:.0f}")
        print(f"  slack<{a:g}|drive>5 played: total margin EUR {tot:.0f} (server {srv:.0f}), runs >= 0.90 on time {ok} of {n}, worst {worst:.3f}")


def stateful_run(rows: list[dict], model, groups: list[str], p_star: float, also: Callable[[dict], bool] = lambda r: True) -> tuple[float, float, int]:
    """Replay of 'decline when P(late) > p_star' in arrival order, with the state the desk would have had: open
    orders and late shares so far counted over the accepted orders only, the request re-scored with them.
    Outcomes of accepted orders stay those of the accept-all week."""
    acc: list[dict] = []
    for r in sorted(rows, key=lambda x: x["arrived"]):
        t = r["arrived"]
        book = sum(1 for o in acc if o["won_at"] <= t and (o["delivered_at"] is None or o["delivered_at"] > t))
        matured = [o for o in acc if o["order_deadline"] < t]
        run_rate = (sum(o["late"] for o in matured) + ONLINE_PRIOR_N * ONLINE_PRIOR_P) / (len(matured) + ONLINE_PRIOR_N)
        town = [o for o in matured if o["pickup"] == r["pickup"]]
        town_rate = (sum(o["late"] for o in town) + TOWN_PRIOR_N * run_rate) / (len(town) + TOWN_PRIOR_N)
        _, xs = design([{**r, "book": book, "run_late_sofar": run_rate, "town_late_sofar": town_rate}], groups, lambda _: {})
        if also(r) and model.prob(xs[0]) <= p_star:
            acc.append(r)
    return 1 - mean(r["late"] for r in acc), sum(r["margin"] for r in acc) / EUR, len(acc)


def s10d_stateful(dev: list[dict], hold: list[dict]) -> None:
    groups = MODELS[CHOSEN]
    print(f"\n## S10d state-consistent replay of P(late) > p*, {CHOSEN}: dev weeks scored by their LOSO fold model, hold by the all-dev model")
    models = {s: fit_predict([r for r in dev if r["seed"] != s], dev[:1], groups)[0] for s in DEV}
    full = fit_predict(dev, dev[:1], groups)[0]
    weeks = defaultdict(list)
    for r in dev + hold:
        if in_regime(r) and unfiltered(r):
            weeks[r["world"]].append(r)
    filt = lambda r: r["slack_h"] >= 6 and r["drive_h"] <= 5
    rules = [(f"P>{t:.2f}", t, lambda r: True) for t in (0.05, 0.10, 0.15, 0.20)] + \
            [(f"P>{t:.2f} or slack<6|drive>5", t, filt) for t in (0.10, 0.15, 0.20, 1.01)]
    tot, ok, worst = Counter(), Counter(), {name: 1.0 for name, _, _ in rules}
    for w, rs in sorted(weeks.items(), key=lambda kv: kv[1][0]["seed"]):
        model = models.get(rs[0]["seed"], full)
        cells = []
        for name, t, also in rules:
            ot, m, n = stateful_run(rs, model, groups, t, also)
            tot[name] += m
            ok[name] += ot >= 1 - GATE
            worst[name] = min(worst[name], ot)
            cells.append(f"{ot:.3f}|{m:5.0f}")
        print(f"  {w} ({rs[0]['seed']}) " + " ".join(cells))
    for name, _, _ in rules:
        print(f"  {name:>28}: total margin EUR {tot[name]:.0f}, runs >= 0.90 on time {ok[name]} of {len(weeks)}, worst on-time {worst[name]:.3f}")


def s7b_variants(dev: list[dict]) -> None:
    print("\n## S7b compact variants compared on LOSO only (picks F): mean within-run AUC, pooled log-loss")
    base = ["day10", "legs", "private", "premium", "book", "online"]
    for name, g in (("one 10h hinge", base), ("+drive", base + ["drive"]), ("+note", base + ["note"]),
                    ("+drive+note (= F)", base + ["drive", "note"]), ("+kind", base + ["kind"]), ("+EV", base + ["ev_low"])):
        oof = loso(dev, g)
        pairs = oof_rows(dev, oof)
        a = mean(within_run_auc([r for r in dev if r["seed"] == s], oof[s]) for s in DEV)
        print(f"  {name:>18}: AUC_in_run {a:.4f}  logloss {logloss([p for _, p in pairs], [int(r['late']) for r, _ in pairs]):.4f}")


def s15_net(pairs_by_label: dict[str, list[tuple[dict, float]]], lam: float) -> None:
    print(f"\n## S15 realized margin per order minus the gate cost lambda*(p-0.10), lambda EUR {lam:.0f}, by P(late) band")
    edges = (0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.01)
    for label, pairs in pairs_by_label.items():
        cells = []
        for lo, hi in zip(edges, edges[1:]):
            sel = [(r, p) for r, p in pairs if lo <= p < hi]
            if sel:
                net = mean(r["margin"] for r, _ in sel) / EUR - lam * (mean(p for _, p in sel) - GATE)
                cells.append(f"{lo:.2f}-{min(hi, 1):.2f}: {net:+6.1f}")
        print(f"  {label}: " + "  ".join(cells))


def budget_run(pairs: list[tuple[dict, float]], target: float, recal: bool, cap: float) -> tuple[float, float, int]:
    """Online decline rule replayed on one run's won orders (offline drop): in arrival order, accept an order when
    its P(late) is at most `target`, or when the projected late share of the accepted book stays at most `target`;
    never above `cap`. Projected late = realized lateness of accepted orders whose deadline has passed + P(late)
    of the rest. recal: scale P(late) by (realized late + 2) / (predicted late + 2) over matured accepted orders."""
    acc: list[tuple[dict, float]] = []
    for r, p in sorted(pairs, key=lambda x: x[0]["arrived"]):
        t = r["arrived"]
        matured = [(o, q) for o, q in acc if o["order_deadline"] < t]
        ratio = (sum(o["late"] for o, _ in matured) + 2) / (sum(q for _, q in matured) + 2) if recal else 1.0
        adj = min(1.0, p * ratio)
        projected = sum(o["late"] for o, _ in matured) + sum(min(1.0, q * ratio) for o, q in acc if o["order_deadline"] >= t)
        if adj <= cap and (adj <= target or (projected + adj) / (len(acc) + 1) <= target):
            acc.append((r, p))
    kept = [r for r, _ in acc]
    return 1 - mean(r["late"] for r in kept), sum(r["margin"] for r in kept) / EUR, len(kept)


def switch_run(pairs: list[tuple[dict, float]], loose: float, tight: float, trigger: float) -> tuple[float, float, int]:
    """Fixed threshold `loose`, tightened to `tight` while the realized late share of accepted orders whose deadline
    has passed is above `trigger` (offline drop, arrival order)."""
    acc: list[tuple[dict, float]] = []
    for r, p in sorted(pairs, key=lambda x: x[0]["arrived"]):
        matured = [o for o, _ in acc if o["order_deadline"] < r["arrived"]]
        late_share = mean(o["late"] for o in matured) if matured else 0.0
        if p <= (tight if late_share > trigger else loose):
            acc.append((r, p))
    kept = [r for r, _ in acc]
    return 1 - mean(r["late"] for r in kept), sum(r["margin"] for r in kept) / EUR, len(kept)


def s13_switch(runs: dict[str, list[tuple[dict, float]]], label: str) -> None:
    print(f"\n## S13b switch rule, {label} (offline drop): decline above 0.20 or 0.15, tightened to 0.10 while the realized late share of matured accepted orders > 0.07")
    for w, pairs in sorted(runs.items(), key=lambda kv: kv[1][0][0]["seed"]):
        cells = [switch_run(pairs, lo, 0.10, 0.07) for lo in (0.20, 0.15)]
        print(f"  {w} ({pairs[0][0]['seed']}) " + "   ".join(f"loose {lo:.2f}: {a:.3f}|{m:6.0f}|{n:3d}" for lo, (a, m, n) in zip((0.20, 0.15), cells)))


def s14_gate_cost(all_rows: list[dict], errs_sd: float) -> float:
    """lambda = V * phi(z) / sigma_L: euros of expected loss per unit of expected late orders, where V is the margin
    of a ranked week, N its won orders, and z the distance of the target late share from the 10% gate in sd units."""
    print("\n## S14 gate shadow price lambda (EUR per unit of P(late) above 0.10)")
    by = defaultdict(list)
    for r in all_rows:
        if in_regime(r) and not unfiltered(r):
            by[r["world"]].append(r)
    ranked = [rs for rs in by.values() if mean(r["late"] for r in rs) <= GATE]
    v = sorted(sum(r["margin"] for r in rs) / EUR for rs in ranked)
    n = sorted(len(rs) for rs in ranked)
    V, N = v[len(v) // 2], n[len(n) // 2]
    print(f"  ranked filtered R runs {len(ranked)}: median margin EUR {V:.0f} (range {v[0]:.0f}-{v[-1]:.0f}), median won orders {N}")
    for target in (0.06, 0.07, 0.08):
        sd = math.sqrt(errs_sd ** 2 + target * (1 - target) / N)
        z = (GATE - target) / sd
        phi = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
        lam = V * phi / (sd * N)
        print(f"  target late share {target:.2f}: sd of late share {sd:.3f}, z {z:.2f}, lambda EUR {lam:.0f} "
              f"(V range gives {v[0] * phi / (sd * N):.0f}-{v[-1] * phi / (sd * N):.0f})")
        if target == 0.07:
            out = lam
    return out


def s13_budget(runs: dict[str, list[tuple[dict, float]]], label: str) -> None:
    print(f"\n## S13 online late-budget rule, {label} (offline drop): on-time share | margin EUR | orders kept")
    settings = [(tg, rc, cap) for tg in (0.06, 0.08) for rc in (False, True) for cap in (0.30,)]
    print("  run (seed)                    " + " ".join(f"t={tg:.2f}{' recal' if rc else '      '} cap={cap:.2f}" for tg, rc, cap in settings))
    for w, pairs in sorted(runs.items(), key=lambda kv: kv[1][0][0]["seed"]):
        cells = [budget_run(pairs, tg, rc, cap) for tg, rc, cap in settings]
        print(f"  {w} ({pairs[0][0]['seed']}) " + " ".join(f"{a:.3f}|{m:6.0f}|{n:3d}          " for a, m, n in cells))


def s11_hold(dev: list[dict], hold: list[dict]) -> dict[str, list[tuple[dict, float]]]:
    print("\n## S11 external check: fit on all 4 dev seeds, predict the 6 hold seeds (never fitted on)")
    preds = {}
    for name, groups in MODELS.items():
        _, ps = fit_predict(dev, hold, groups)
        print(f"- {name}")
        for s in HOLD:
            sel = [(r, p) for r, p in zip(hold, ps) if r["seed"] == s]
            print(f"  {s}: {fmt(metrics([r for r, _ in sel], [p for _, p in sel]))}")
        print(f"  pooled: {fmt(metrics(hold, ps))}")
        if name == CHOSEN:
            preds = {w: [(r, p) for r, p in zip(hold, ps) if r["world"] == w] for w in {r["world"] for r in hold}}
    return preds


def s12_gate(dev_r_pairs: list[tuple[dict, float]], hold_preds: dict[str, list[tuple[dict, float]]]) -> float:
    print("\n## S12 gate inputs: per run in regime R (unfiltered), observed vs predicted late share of all won orders")
    errs = []
    for label, groups in (("dev OOF", _by_world(dev_r_pairs)), ("hold", hold_preds)):
        for w, pairs in sorted(groups.items(), key=lambda kv: kv[1][0][0]["seed"]):
            if not unfiltered(pairs[0][0]):
                continue
            obs, pred = mean(r["late"] for r, _ in pairs), mean(p for _, p in pairs)
            errs.append(obs - pred)
            print(f"  {label} {w} ({pairs[0][0]['seed']}): n {len(pairs)} obs {obs:.3f} pred {pred:.3f} diff {obs - pred:+.3f} "
                  f"margin EUR {sum(r['margin'] for r, _ in pairs) / EUR:.0f}")
    print(f"  run-level error obs-pred: mean {mean(errs):+.3f} sd {pstdev(errs):.3f} max {max(errs):+.3f} over {len(errs)} runs")
    return pstdev(errs)


def _by_world(pairs: list[tuple[dict, float]]) -> dict[str, list[tuple[dict, float]]]:
    out = defaultdict(list)
    for r, p in pairs:
        out[r["world"]].append((r, p))
    return dict(out)


def main() -> None:
    dev, dinfo = load(None)
    hold, hinfo = load(HOLD_PINNED)
    s1_data(dev, hold, dinfo, hinfo)
    s1b_win_vs_price(dev)
    s1c_label_check(dev + hold)
    s2_univariate(dev)
    s3_places(dev)
    oofs = s4_loso(dev)
    chosen = oof_rows(dev, oofs[CHOSEN])
    s5_calibration(chosen, f"{CHOSEN}, dev out-of-fold, all regimes")
    s5_calibration([(r, p) for r, p in chosen if in_regime(r)], f"{CHOSEN}, dev out-of-fold, regime R")
    s6_coefficients(dev, CHOSEN)
    s6_coefficients(dev, "E B' + online")
    s6_coefficients(dev, "B task features")
    s7_drop_one(dev, "B task features")
    s7_drop_one(dev, "E B' + online")
    s7b_variants(dev)
    sev = s8_severity(dev, hold)
    r_pairs = [(r, p) for r, p in chosen if in_regime(r)]
    s9_economics(r_pairs, sev)
    hold_preds = s11_hold(dev, hold)
    s9_economics([rp for v in hold_preds.values() for rp in v], sev)
    dev_unf = {w: v for w, v in _by_world(r_pairs).items() if unfiltered(v[0][0])}
    decline_table(dev_unf, "dev regime R unfiltered runs, LOSO predictions")
    decline_table({w: v for w, v in hold_preds.items() if unfiltered(v[0][0])}, "hold unfiltered runs, fit on all dev")
    rule_check(dev + hold, {**_by_world(r_pairs), **hold_preds})
    err_sd = s12_gate(r_pairs, hold_preds)
    hold_unf = {w: v for w, v in hold_preds.items() if unfiltered(v[0][0])}
    s13_budget(dev_unf, "dev regime R unfiltered runs, LOSO predictions")
    s13_budget(hold_unf, "hold unfiltered runs, fit on all dev")
    s13_switch(dev_unf, "dev regime R unfiltered runs")
    s13_switch(hold_unf, "hold unfiltered runs")
    lam = s14_gate_cost(dev + hold, err_sd)
    s15_net({"dev R (LOSO)": r_pairs, "hold (fit on dev)": [rp for v in hold_preds.values() for rp in v]}, lam)
    s10c_compare({**dev_unf, **hold_unf}, 0.15)
    s10c_real(dev + hold)
    s10d_stateful(dev, hold)


if __name__ == "__main__":
    main()
