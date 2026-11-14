"""Builds proof/push.html, the evidence for step 6 (the margin push), from evidence/sweeps/push1.json and push2.json.

    python -m tools.proof_push [rehearsal world id]
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from tools.proof_g0 import TEMPLATE as G0_TEMPLATE, eur, status

ROOT = Path(__file__).resolve().parents[1]
SWEEPS = ROOT / "evidence" / "sweeps"
OUT = ROOT / "proof" / "push.html"
NAMES = {
    ("push1", 0): "C · opening fee 1.0× (control)",
    ("push1", 1): "Opening fee 0.9×",
    ("push1", 2): "Opening fee 0.8×",
    ("push1", 3): "Win target 50%",
    ("push1", 4): "0.9× fee + 50% target",
    ("push2", 0): "0.9×, cap 3 h before last pickup",
    ("push2", 1): "0.9×, intake cap 70",
    ("push2", 2): "0.85×, cap 3 h before last pickup",
}
CHOSEN = ("push1", 1)
SAFER = ("push2", 1)


def arms() -> list[dict]:
    out = []
    for name in ("push1", "push2"):
        r = json.loads((SWEEPS / f"{name}.json").read_text(encoding="utf-8"))
        for i, st in enumerate(r["settings"]):
            rows = {x["seed"]: x for x in r["rows"] if x["setting"] == st}
            scores = [rows[s]["score"] for s in r["seeds"] if rows[s].get("score")]
            out.append({"key": (name, i), "label": NAMES[(name, i)], "setting": st, "seeds": r["seeds"], "rows": rows,
                        "total": sum(s["marginCents"] for s in scores), "worst": min(s["onTimeShare"] for s in scores),
                        "ranked": sum(s["onTimeShare"] >= 0.9 for s in scores), "n": len(scores), "clean": r.get("serverClean")})
    return out


def frontier(all_arms: list[dict]) -> str:
    w, h, left, right, top, bottom = 720, 300, 70, 190, 16, 40
    xs = (0.905, 0.955)
    ys = (66000, 77000)
    x = lambda v: left + (w - left - right) * (v - xs[0]) / (xs[1] - xs[0])
    y = lambda v: top + (h - top - bottom) * (ys[1] - v) / (ys[1] - ys[0])
    parts = []
    for t in (0.91, 0.92, 0.93, 0.94, 0.95):
        parts.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{h - bottom}" class="{"ref" if t == 0.92 else "grid"}"/>'
                     f'<text x="{x(t):.1f}" y="{h - bottom + 16}" class="tick" text-anchor="middle">{t * 100:.0f}%</text>')
    for v in range(66000, 77001, 2000):
        parts.append(f'<line x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                     f'<text x="{left - 8}" y="{y(v) + 4:.1f}" class="tick" text-anchor="end">€{v / 1000:.0f}K</text>')
    parts.append(f'<text x="{x(0.92) + 4:.1f}" y="{top + 10}" class="tick">selection line: worst week ≥ 92%</text>')
    parts.append(f'<text x="{(left + w - right) / 2:.1f}" y="{h - 4}" class="tick" text-anchor="middle">worst week on time (of 8)</text>')
    for a in all_arms:
        cx, cy = x(a["worst"]), y(a["total"] / 100)
        cls = "chosen" if a["key"] == CHOSEN else "safer" if a["key"] == SAFER else "control" if a["key"] == ("push1", 0) else "other"
        tip = html.escape(f"<b>{a['label']}</b><br>margin {eur(a['total'])} over 8 weeks<br>worst week {a['worst'] * 100:.1f}% · ranked {a['ranked']}/{a['n']}")
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" class="{cls}" data-tip="{tip}"/>')
        if cls != "other":  # selective direct labels; the others are in the table and the tooltip
            parts.append(f'<text x="{cx + 9:.1f}" y="{cy + (14 if cls == "safer" else 4):.1f}" class="tick">{html.escape(a["label"])}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Margin against worst-week on-time share for each policy">{"".join(parts)}</svg>'


def table(all_arms: list[dict]) -> str:
    seeds = all_arms[0]["seeds"]
    rows = []
    for a in all_arms:
        cells = []
        for s in seeds:
            sc = a["rows"][s].get("score")
            cells.append("<td>—</td>" if not sc else f'<td>{sc["onTimeShare"] * 100:.1f}%<br><span class="sub">{eur(sc["marginCents"])}</span></td>')
        mark = " ★" if a["key"] == CHOSEN else ""
        rows.append(f"<tr><th scope=row>{html.escape(a['label'])}{mark}</th>{''.join(cells)}<td>{a['ranked']}/{a['n']}</td><td>{a['worst'] * 100:.1f}%</td><td>{eur(a['total'])}</td></tr>")
    head = "".join(f"<th scope=col>{s}</th>" for s in seeds)
    return f'<div class="scroll"><table><thead><tr><th scope=col>Policy</th>{head}<th scope=col>Ranked</th><th scope=col>Worst</th><th scope=col>Total</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def page(rehearsal: dict | None) -> str:
    all_arms = arms()
    by = {a["key"]: a for a in all_arms}
    c, chosen, safer = by[("push1", 0)], by[CHOSEN], by[SAFER]
    banner = status("good", f"Opening fee 0.9×: {eur(chosen['total'] - c['total'])} over 8 weeks ({(chosen['total'] / c['total'] - 1) * 100:.1f}%), ranked 8/8, worst week {chosen['worst'] * 100:.1f}%")
    tile = lambda label, value, sub: f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'
    tiles = "".join([
        tile("Margin per L8 week", eur(chosen["total"] // 8), f"policy C: {eur(c['total'] // 8)}"),
        tile("Worst week on time", f"{chosen['worst'] * 100:.1f}%", f"policy C: {c['worst'] * 100:.1f}%; safer option (intake cap 70): {safer['worst'] * 100:.1f}%"),
        tile("Reproducible", "8/8 weeks", "policy C gave the same margin to the cent as in the step 5 sweep; canary clean in both rounds"),
    ])
    if rehearsal:
        sc = rehearsal["score"]
        tiles += tile("Live rehearsal (2×, killed)", f"{sc['wonOrders']} orders", f"{sc['onTimeShare'] * 100:.1f}% on time · {eur(sc['marginCents'])}; {rehearsal['outcomes'].get('unquoted', 0)} unquoted while killed")
    body = f"""
<h1>Step 6 · Paying drivers less, carefully</h1>
<p>Driver fees took 67-81% of revenue, and most gigs were booked at the very first fee shown: the desk opened higher than drivers needed. A lower opening fee, with the same schedule rising to 2× the typical fee before the last pickup time, keeps the cars moving and pays less. Every arm below ran on the same eight L8 weeks as policy C, including the four hardest.</p>
<div class="banner">{banner}</div>
<div class="tiles">{tiles}</div>
<h2>Margin against safety, one dot per policy</h2>
<div class="card"><div class="legend"><span><span class="keydot" style="background:var(--s1)"></span>chosen</span><span><span class="keydot" style="background:var(--s3)"></span>safer alternative</span><span><span class="keydot" style="background:var(--muted)"></span>control (C)</span><span><span class="keydot" style="background:var(--axis)"></span>other</span></div>
{frontier(all_arms)}
<p class="note">Every cheaper opening fee earns €4,100-6,900 more over 8 weeks and costs 2-3.5 points on the worst week (always dev-3 or v4-5); all stay ranked. The rule fixed before the runs: worst week ≥ 92%, then the most margin. A higher win target adds nothing.</p></div>
{table(all_arms)}
<p class="note">Built by <code>python -m tools.proof_push</code> from evidence/sweeps/push1.json and push2.json.</p>
"""
    head = G0_TEMPLATE.split("<main>")[0].replace("Spread G0 proof", "Spread margin push proof").replace(
        ".routes{{", ".sub{{color:var(--muted);font-size:11px}}.ref{{stroke:var(--critical);stroke-width:1;stroke-dasharray:4 3}}"
                     ".chosen{{fill:var(--s1);stroke:var(--surface);stroke-width:2}}.safer{{fill:var(--s3);stroke:var(--surface);stroke-width:2}}"
                     ".control{{fill:var(--muted);stroke:var(--surface);stroke-width:2}}.other{{fill:var(--axis);stroke:var(--surface);stroke-width:2}}.routes{{").replace(
        "--s2:#eb6834;", "--s2:#eb6834;--s3:#1baf7a;").replace("--s2:#d95926;", "--s2:#d95926;--s3:#199e70;")
    return head.format() + "<main>" + body + "</main>" + G0_TEMPLATE.split("</main>")[1].format()


def main() -> None:
    rehearsal = json.loads((ROOT / "evidence" / "rehearsal" / f"{sys.argv[1]}.json").read_text(encoding="utf-8")) if len(sys.argv) > 1 else None
    OUT.write_text(page(rehearsal), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
