"""Builds proof/policy.html, the evidence for step 3 (our policy), from the saved sweeps only.

    python -m tools.proof_policy
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.proof_g0 import TEMPLATE as G0_TEMPLATE, eur, status

ROOT = Path(__file__).resolve().parents[1]
SWEEPS = ROOT / "evidence" / "sweeps"
OUT = ROOT / "proof" / "policy.html"
PERTURBED = {"wc721c95a136b417e5d7c"}  # replayed by the kit client's double send (see the spec's decision log)
FEES = "fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2"
BEST = f"priced price_mult=1.5 {FEES} min_slack_h=6 max_drive_h=5"


def rows(name: str) -> list[dict]:
    data = json.loads((SWEEPS / f"{name}.json").read_text(encoding="utf-8"))
    return [r for r in data["rows"] if r.get("score") and r["worldId"] not in PERTURBED]


def pick(rs: list[dict], setting: str, seed: str) -> dict | None:
    return next((r for r in rs if r["setting"] == setting and r["seed"] == seed), None)


def cell(r: dict | None) -> str:
    if not r:
        return "<td>—</td>"
    s = r["score"]
    ok = s["onTimeShare"] >= 0.9
    return (f'<td class="{"" if ok else "bad"}">{s["onTimeShare"] * 100:.1f}%{" ✓" if ok else ""}<br><span class="sub">{eur(s["marginCents"])} · {s["wonOrders"]} won</span></td>')


def price_chart(points: dict[str, list[tuple[float, float, float]]]) -> str:
    """Two small multiples on one x axis (× list): margin and on-time share, one line per seed."""
    w, h, left, right, top, bottom, gap = 720, 230, 64, 80, 14, 34, 40
    pw = (w - left - right - gap) / 2
    xs = sorted({x for pts in points.values() for x, _, _ in pts})
    x = lambda v, off: left + off + pw * (v - xs[0]) / (xs[-1] - xs[0])
    colours = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"]
    parts = []
    for panel, (idx, lo, hi, ticks, fmt, title) in enumerate([
        (1, -100000, 10000, [-100000, -50000, 0], lambda v: f"{'−' if v < 0 else ''}€{abs(v) / 1000:.0f}K", "Margin, € per week"),
        (2, 0.4, 1.0, [0.4, 0.6, 0.8, 0.9, 1.0], lambda v: f"{v * 100:.0f}%", "On-time share"),
    ]):
        off = panel * (pw + gap)
        y = lambda v: top + (h - top - bottom) * (hi - v) / (hi - lo)
        parts.append(f'<text x="{left + off}" y="{top - 2}" class="tick" font-weight="600">{title}</text>')
        for t in ticks:
            cls = "ref" if (idx == 2 and t == 0.9) or (idx == 1 and t == 0) else "grid"
            parts.append(f'<line x1="{left + off}" x2="{left + off + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="{cls}"/>'
                         f'<text x="{left + off - 6}" y="{y(t) + 4:.1f}" class="tick" text-anchor="end">{fmt(t)}</text>')
        for v in xs:
            parts.append(f'<text x="{x(v, off):.1f}" y="{h - 12}" class="tick" text-anchor="middle">{v:g}×</text>')
        for i, (seed, pts) in enumerate(points.items()):
            pts = sorted(pts)
            vals = [(px, py / 100 if idx == 1 else py2) for px, py, py2 in pts]
            d = " ".join(f"{'M' if j == 0 else 'L'}{x(px, off):.1f},{y(max(lo, min(hi, v))):.1f}" for j, (px, v) in enumerate(vals))
            parts.append(f'<path d="{d}" fill="none" stroke="{colours[i]}" stroke-width="2"/>')
            for px, v in vals:
                tip = html.escape(f"<b>{seed}, {px:g}× list</b><br>" + (f"margin {eur(int(v * 100))}" if idx == 1 else f"on time {v * 100:.1f}%"))
                parts.append(f'<circle cx="{x(px, off):.1f}" cy="{y(max(lo, min(hi, v))):.1f}" r="4" fill="{colours[i]}" stroke="var(--surface)" stroke-width="2" data-tip="{tip}"/>')
    legend = "".join(f'<span><span class="key" style="background:{colours[i]}"></span>{html.escape(s)}</span>' for i, s in enumerate(points))
    return f'<div class="legend">{legend}</div><svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Margin and on-time share by price multiplier">{"".join(parts)}</svg>'


def page() -> str:
    price1, fees1, select1, hold = rows("price1"), rows("fees1"), rows("select1"), rows("holdout1")
    points: dict[str, list] = {}
    for seed in ("dev-1", "dev-2"):
        for m in ("1.0", "1.2", "1.35", "1.5", "1.65", "1.8"):
            r = pick(price1, f"priced price_mult={m}", seed) or pick(fees1, f"priced price_mult={m}", seed)
            if r:
                points.setdefault(seed, []).append((float(m), r["score"]["marginCents"], r["score"]["onTimeShare"]))
    dev = ["dev-1", "dev-2", "dev-3", "dev-4"]
    ladder = [
        ("Starter (1.0× list, starter fees)", "price1", "priced price_mult=1.0"),
        ("Idea 1: price 1.5× list", "fees1", "priced price_mult=1.5"),
        ("+ Idea 2: fees rise to 2× before the last pickup", "fees1", f"priced price_mult=1.5 {FEES}"),
        ("+ Idea 3: decline slack < 6 h or drive > 5 h", "select1", BEST),
    ]
    by_name = {"price1": price1, "fees1": fees1, "select1": select1}
    ladder_rows = []
    for label, name, setting in ladder:
        rs = [pick(by_name[name], setting, s) for s in dev]
        got = [r for r in rs if r]
        total = sum(r["score"]["marginCents"] for r in got)
        ranked = sum(r["score"]["onTimeShare"] >= 0.9 for r in got)
        ladder_rows.append(f"<tr><th scope=row>{html.escape(label)}</th>{''.join(cell(r) for r in rs)}<td>{ranked}/{len(got)}</td><td>{eur(total)}</td></tr>")
    hold_seeds = [f"hold-{i}" for i in range(1, 7)]
    hold_rows = []
    for label, setting in [("Ideas 1+2 (no decline)", f"priced price_mult=1.5 {FEES}"), ("Ideas 1+2+3 (best rule)", BEST)]:
        rs = [pick(hold, setting, s) for s in hold_seeds]
        got = [r for r in rs if r]
        hold_rows.append(f"<tr><th scope=row>{label}</th>{''.join(cell(r) for r in rs)}<td>{sum(r['score']['onTimeShare'] >= 0.9 for r in got)}/{len(got)}</td>"
                         f"<td>{eur(sum(r['score']['marginCents'] for r in got))}</td></tr>")
    best_dev = [pick(select1, BEST, s) for s in dev]
    best_hold = [pick(hold, BEST, s) for s in hold_seeds]
    all_best = [r for r in best_dev + best_hold if r]
    ranked_all = sum(r["score"]["onTimeShare"] >= 0.9 for r in all_best)
    total_all = sum(r["score"]["marginCents"] for r in all_best)
    starter = [pick(price1, "priced price_mult=1.0", s) for s in ("dev-1", "dev-2")]
    banner = status("good" if ranked_all == len(all_best) else "critical",
                    f"Best rule: ranked on {ranked_all} of {len(all_best)} L8 weeks, margin {eur(total_all)} over {len(all_best)} weeks")
    tile = lambda label, value, sub: f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'
    tiles = "".join([
        tile("Margin per L8 week, best rule", eur(total_all // max(1, len(all_best))), f"mean of {len(all_best)} weeks (4 dev + 6 hold-out)"),
        tile("Starter on the same dev weeks", eur(sum(r["score"]["marginCents"] for r in starter if r) // 2), "dev-1 and dev-2; it wins ~90% of requests at list"),
        tile("Ranked weeks", f"{ranked_all}/{len(all_best)}", "≥ 90% of won orders on time"),
        tile("House best, current round", "≈ +€12,090", "mean of 5 secret L8 worlds (public board)"),
    ])
    body = f"""
<h1>Step 3 · Our policy</h1>
<p>Three ideas, each added on top of the kit's logistics and measured on the same L8 weeks (paired seeds), then checked on six hold-out weeks it was never tuned on. All numbers are the server's end-of-week score.</p>
<div class="banner">{banner}</div>
<div class="tiles">{tiles}</div>
<h2>Idea 1: price above list, win fewer cars</h2>
<p>At level 8 the competitor charges 26–54% above list, so quoting list wins almost everything, far more than the drivers can carry. Raising the multiplier trades volume for margin and on-time share. The best multiplier differs by world.</p>
<div class="card">{price_chart(points)}</div>
<h2>The ladder: each idea on the same four dev weeks</h2>
<div class="scroll"><table><thead><tr><th scope=col>Policy</th>{''.join(f'<th scope=col>{s}</th>' for s in dev)}<th scope=col>Ranked</th><th scope=col>Total margin</th></tr></thead><tbody>{''.join(ladder_rows)}</tbody></table></div>
<p class="note">Idea 2: a fee schedule that opens at the typical fee and reaches 2× two hours before the order's last pickup time; the starter only raised fees after the deadline warning, and 78% of its late orders were booked after that time. Idea 3: cars with less than 6 h of slack (deadline − ready time − driving) or more than 5 h of driving are declined by quoting 4× list; they were late 40–66% of the time.</p>
<h2>Hold-out: six weeks the rules were not tuned on</h2>
<div class="scroll"><table><thead><tr><th scope=col>Policy</th>{''.join(f'<th scope=col>{s}</th>' for s in hold_seeds)}<th scope=col>Ranked</th><th scope=col>Total margin</th></tr></thead><tbody>{''.join(hold_rows)}</tbody></table></div>
<p>Two hold-out weeks miss the 90% gate (89.0% and 86.7%). Fixed thresholds do not suit every world: the next idea is to adapt within the week, raising the price when the week's on-time share or driver backlog says the desk is taking too much.</p>
<h2>What the runs taught about robustness</h2>
<p>Some weeks did not reproduce. The cause was on our side of the wire: on an unstable network, the kit's client resends a request whose connection broke after the server had received it, so the server applied it twice (two gigs for one car, a clock moved twice, events lost). The desk now uses a client that never sends a POST twice and lets the core recover from the world's own state, and it refills any gap in the event sequence. With that, 18 kills at random moments still give the identical week (step 2 page).</p>
<p class="note">Built by <code>python -m tools.proof_policy</code> from evidence/sweeps/*.json. Sweeps price1, fees1, select1 and holdout1 ran before the canary existed; one row known to be replayed twice (wc721c95…) is excluded.</p>
"""
    head = G0_TEMPLATE.split("<main>")[0].replace("Spread G0 proof", "Spread policy proof").replace(
        ".routes{{", ".ref{{stroke:var(--critical);stroke-width:1;stroke-dasharray:4 3}}.sub{{color:var(--muted);font-size:11px}}.routes{{").replace(
        "--s2:#eb6834;", "--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;").replace("--s2:#d95926;", "--s2:#d95926;--s3:#199e70;--s4:#c98500;")
    return head.format() + "<main>" + body + "</main>" + G0_TEMPLATE.split("</main>")[1].format()


def main() -> None:
    OUT.write_text(page(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
