"""Builds proof/push8.html, the evidence for step 8 (the second margin push after test final 2), from the
round sweeps (evidence/sweeps/push3..), the hold-out sweep and the test final 2 reveal.

    python -m tools.proof_push8 [rehearsal world id]
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from tools.proof_g0 import TEMPLATE as G0_TEMPLATE, eur, status

ROOT = Path(__file__).resolve().parents[1]
SWEEPS = ROOT / "evidence" / "sweeps"
OUT = ROOT / "proof" / "push8.html"
ROUNDS = ["push3", "push4", "push5", "push6", "push7"]
HOLDOUT = ["holdout9"]  # 16 fresh seeds (its ho8 half reran holdout8 to the cent)
CURRENT = "options=first min_slack_h=6 max_drive_h=5"   # the final policy before step 8
CHOSEN = "options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
LABELS = {
    "options": "options", "max_drive_h": "drive ≤", "min_slack_h": "slack ≥", "night_hold": "night hold",
    "batch_cap": "batch cap", "fee_open": "opening fee", "intake_cap": "intake cap", "target_win": "win target",
    "long_slack_h": "long drive if slack ≥", "lane_k": "lane factor", "cost_markup": "cost markup",
    "long_drive_h": "long drive from", "long_lead_h": "long-drive cap lead h", "long_cap": "long-drive cap",
}
DEFAULTS = {"options": "first", "min_slack_h": "6", "max_drive_h": "5", "fee_open": "0.9", "intake_cap": "80", "target_win": "0.4"}


def words(setting: str) -> dict[str, str]:
    """A setting's parameters, with the pre-step-8 defaults filled in where a round left them out."""
    params = dict(w.split("=", 1) for w in setting.split()[1:])
    return {**DEFAULTS, **params}


def levers(params: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in {**DEFAULTS, **params}.items() if k in LABELS}


def matches(setting: str, spec: str) -> bool:
    """Whether a setting has exactly the spec's values on the step 8 levers (the rest is the shared base)."""
    return levers(words(setting)) == levers(dict(w.split("=", 1) for w in spec.split()))


def label(setting: str, common: set) -> str:
    """The step 8 levers where the arm differs from the policy before step 8 (`common` is kept for callers)."""
    parts = [f"{LABELS[k]} {v}" for k, v in levers(words(setting)).items() if DEFAULTS.get(k) != v]
    return ", ".join(parts) or "policy before step 8"


def load(names: list[str]) -> list[dict]:
    arms = []
    for name in names:
        path = SWEEPS / f"{name}.json"
        if not path.exists():
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        common = set.intersection(*(set(words(s).items()) for s in r["settings"])) if len(r["settings"]) > 1 else set()
        common = {f"{k}={v}" for k, v in common}
        for st in r["settings"]:
            rows = {x["seed"]: x for x in r["rows"] if x["setting"] == st}
            scores = [rows[s]["score"] for s in r["seeds"] if rows.get(s, {}).get("score")]
            if not scores:
                continue
            arms.append({"sweep": name, "setting": st, "label": label(st, common), "seeds": r["seeds"], "rows": rows,
                         "total": sum(s["marginCents"] for s in scores), "worst": min(s["onTimeShare"] for s in scores),
                         "ranked": sum(s["onTimeShare"] >= 0.9 for s in scores), "n": len(r["seeds"]),
                         "orders": sum(s["wonOrders"] for s in scores), "clean": r.get("serverClean")})
    return arms


def pick(arms: list[dict], spec: str, sweep: str | None = None) -> dict | None:
    found = [a for a in arms if matches(a["setting"], spec) and (sweep is None or a["sweep"] == sweep)]
    return found[0] if found else None


def frontier(arms: list[dict], chosen: dict | None, current: dict | None) -> str:
    w, h, left, right, top, bottom = 720, 320, 70, 30, 16, 40
    worsts = [a["worst"] for a in arms] or [0.9]
    totals = [a["total"] / 100 for a in arms] or [0]
    xs = (min(0.86, min(worsts) - 0.005), max(0.96, max(worsts) + 0.005))
    lo, hi = (min(totals) // 5000) * 5000, (max(totals) // 5000 + 1) * 5000
    x = lambda v: left + (w - left - right) * (v - xs[0]) / (xs[1] - xs[0])
    y = lambda v: top + (h - top - bottom) * (hi - v) / (hi - lo)
    parts = []
    t = round(xs[0] + 0.005, 2)
    while t <= xs[1]:
        parts.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{h - bottom}" class="{"ref" if abs(t - 0.92) < 1e-9 else "grid"}"/>'
                     f'<text x="{x(t):.1f}" y="{h - bottom + 16}" class="tick" text-anchor="middle">{t * 100:.0f}%</text>')
        t = round(t + 0.02, 2)
    v = lo
    while v <= hi:
        parts.append(f'<line x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                     f'<text x="{left - 8}" y="{y(v) + 4:.1f}" class="tick" text-anchor="end">€{v / 1000:.0f}K</text>')
        v += 5000
    parts.append(f'<text x="{x(0.92) + 4:.1f}" y="{top + 10}" class="tick">worst week ≥ 92%</text>')
    parts.append(f'<text x="{(left + w - right) / 2:.1f}" y="{h - 4}" class="tick" text-anchor="middle">worst week on time (of 8 tuning weeks)</text>')
    for a in arms:
        cls = "chosen" if a is chosen else "control" if a is current else "other"
        tip = html.escape(f"<b>{a['label']}</b> ({a['sweep']})<br>margin {eur(a['total'])} over 8 weeks<br>worst week {a['worst'] * 100:.1f}% · ranked {a['ranked']}/{a['n']}")
        parts.append(f'<circle cx="{x(a["worst"]):.1f}" cy="{y(a["total"] / 100):.1f}" r="{7 if cls != "other" else 5}" class="{cls}" data-tip="{tip}"/>')
    for a, name in ((chosen, "chosen"), (current, "final policy before step 8")):
        if a:
            parts.append(f'<text x="{x(a["worst"]) + 10:.1f}" y="{y(a["total"] / 100) + 4:.1f}" class="tick">{name}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Margin against worst-week on-time share for every arm">{"".join(parts)}</svg>'


def seed_table(arms: list[dict]) -> str:
    seeds = arms[0]["seeds"]
    rows = []
    for a in arms:
        cells = "".join("<td>—</td>" if not a["rows"].get(s, {}).get("score") else
                        f'<td>{a["rows"][s]["score"]["onTimeShare"] * 100:.1f}%<br><span class="sub">{eur(a["rows"][s]["score"]["marginCents"])}</span></td>'
                        for s in seeds)
        rows.append(f"<tr><th scope=row>{html.escape(a['title'])}</th>{cells}<td>{a['ranked']}/{a['n']}</td><td>{a['worst'] * 100:.1f}%</td><td>{eur(a['total'])}</td></tr>")
    head = "".join(f"<th scope=col>{s}</th>" for s in seeds)
    return f'<div class="scroll"><table><thead><tr><th scope=col>Policy</th>{head}<th scope=col>Ranked</th><th scope=col>Worst</th><th scope=col>Total</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def tf2_numbers() -> dict:
    board = json.loads((ROOT / "evidence" / "rehearsal" / "tf2_leaderboard.json").read_text(encoding="utf-8"))
    ranked = [t for t in board["teams"] if t["ranked"]]
    mine = next(t for t in board["teams"] if t["team"] == "fluiidd")
    return {"rank": mine["rank"], "of": len(ranked), "margin": mine["marginCents"], "orders": mine["wonOrders"],
            "top10": ranked[9]["marginCents"], "played": len(board["teams"])}


def page(rehearsal: dict | None) -> str:
    tuning = load(ROUNDS)
    holdout = load(HOLDOUT)
    current = pick(tuning, CURRENT, "push3")
    chosen = next((a for a in reversed(tuning) if matches(a["setting"], CHOSEN)), None)
    ho_cur, ho_new = pick(holdout, CURRENT), next((a for a in reversed(holdout) if matches(a["setting"], CHOSEN)), None)
    tf2 = tf2_numbers()
    gain = (chosen["total"] - current["total"]) if chosen and current else 0
    ho_gain = (ho_new["total"] - ho_cur["total"]) if ho_new and ho_cur else None
    banner = status("good" if ho_new and ho_new["ranked"] == ho_new["n"] else "warn",
                    f"Chosen policy: {eur(gain)} over {chosen['n']} tuning weeks ({gain / current['total'] * 100:+.1f}%), "
                    + (f"{eur(ho_gain)} over {ho_new['n']} fresh weeks ({ho_gain / ho_cur['total'] * 100:+.1f}%), ranked {ho_new['ranked']}/{ho_new['n']}, worst {ho_new['worst'] * 100:.1f}%"
                       if ho_gain is not None else "hold-out pending"))
    tile = lambda lab, value, sub: f'<div class="tile"><div class="label">{lab}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'
    tiles = "".join([
        tile("Test final 2", f"rank {tf2['rank']} of {tf2['of']}", f"{eur(tf2['margin'])}, {tf2['orders']} orders; top 10 from {eur(tf2['top10'])}"),
        tile("Margin per L8 week", eur(chosen["total"] // chosen["n"]), f"before step 8: {eur(current['total'] // current['n'])} (same {chosen['n']} tuning weeks)"),
        tile("Per fresh week", eur(ho_new["total"] // ho_new["n"]) if ho_new else "—", f"before step 8: {eur(ho_cur['total'] // ho_cur['n'])} ({ho_new['n']} weeks)" if ho_cur and ho_new else ""),
        tile("Worst week on time", f"{chosen['worst'] * 100:.1f}%", f"fresh weeks: {ho_new['worst'] * 100:.1f}%" if ho_new else ""),
    ])
    if rehearsal:
        sc = rehearsal["score"]
        tiles += tile("Live rehearsal (killed)", f"{sc['wonOrders']} orders",
                      f"{sc['onTimeShare'] * 100:.1f}% on time · {eur(sc['marginCents'])}; {rehearsal['outcomes'].get('unquoted', 0)} unquoted")
    for a, title in ((current, "Final policy before step 8"), (chosen, "Chosen (step 8)")):
        if a:
            a["title"] = title
    for a, title in ((ho_cur, "Before step 8 (fresh weeks)"), (ho_new, "Chosen (fresh weeks)")):
        if a:
            a["title"] = title
    body = f"""
<h1>Step 8 · Turning down less, after test final 2</h1>
<p>Test final 2 ran cleanly (every request quoted in time, one dropped connection recovered in 3.6 s) but ranked {tf2['rank']} of {tf2['of']}: the desk declined 337 of 1030 requests. 166 of them only because the fastest option was too tight, though a slower option the dealer also offered had a day of slack. The desk now quotes every option that passes the risk test instead of judging the first option alone, the limits were re-tuned with that rule (drives up to 6 h, at least 8 h of slack), and fee raises wait for the morning (no driver reads the app from 23:00 to 07:00, so a raise at night only pays the first driver who looks at 07:00). Every arm ran on the same eight L8 weeks; the chosen policy and the policy before step 8 were then compared on sixteen fresh weeks that no choice was made on. Long drives with earlier, higher fees, a cap per bulk batch and a lower opening fee were tried and lost money.</p>
<div class="banner">{banner}</div>
<div class="tiles">{tiles}</div>
<h2>Margin against safety, one dot per arm</h2>
<div class="card"><div class="legend"><span><span class="keydot" style="background:var(--s1)"></span>chosen</span><span><span class="keydot" style="background:var(--muted)"></span>final policy before step 8</span><span><span class="keydot" style="background:var(--axis)"></span>other arms</span></div>
{frontier(tuning, chosen, current)}
<p class="note">The rule fixed before the runs: ranked on every week, worst week ≥ 92%, then the most margin, then confirmed on fresh weeks. Hover a dot for its arm.</p></div>
<h2>Sixteen fresh weeks (never used to choose)</h2>
{seed_table([a for a in (ho_cur, ho_new) if a]) if ho_new and ho_cur else '<p>pending</p>'}
<h2>Tuning weeks</h2>
{seed_table([a for a in (current, chosen) if a])}
<p class="note">Built by <code>python -m tools.proof_push8</code> from evidence/sweeps/{', '.join(ROUNDS + HOLDOUT)}.json (those that exist) and evidence/rehearsal/tf2_*.json.</p>
"""
    head = G0_TEMPLATE.split("<main>")[0].replace("Spread G0 proof", "Spread step 8 proof").replace(
        ".routes{{", ".sub{{color:var(--muted);font-size:11px}}.ref{{stroke:var(--critical);stroke-width:1;stroke-dasharray:4 3}}"
                     ".chosen{{fill:var(--s1);stroke:var(--surface);stroke-width:2}}"
                     ".control{{fill:var(--muted);stroke:var(--surface);stroke-width:2}}.other{{fill:var(--axis);stroke:var(--surface);stroke-width:2}}.routes{{")
    return head.format() + "<main>" + body + "</main>" + G0_TEMPLATE.split("</main>")[1].format()


def main() -> None:
    rehearsal = json.loads((ROOT / "evidence" / "rehearsal" / f"{sys.argv[1]}.json").read_text(encoding="utf-8")) if len(sys.argv) > 1 else None
    OUT.write_text(page(rehearsal), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
