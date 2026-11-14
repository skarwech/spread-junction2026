"""Builds proof/adapt.html, the evidence for step 5 (the adaptive price), from saved files only.

    python -m tools.proof_adapt

The multiplier's path in each world is replayed from that world's journal: the controller is a pure function
of events, so the replay is the path the desk followed.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from desk.journal import load
from desk.policy import Learning, Params, declined
from tools.proof_g0 import TEMPLATE as G0_TEMPLATE, eur, status

ROOT = Path(__file__).resolve().parents[1]
SWEEPS = ROOT / "evidence" / "sweeps"
OUT = ROOT / "proof" / "adapt.html"
LABELS = {0: "A · fixed 1.5× (current)", 1: "B · adaptive, 30% target", 2: "C · adaptive, 40% target", 3: "D · as B, no trust markup", 4: "E · as C, slack 4 h"}


def params_of(setting: str) -> Params:
    return Params.parse(setting.split()[1:])


def path_of(world_id: str, params: Params) -> list[tuple[int, float]]:
    learning = Learning(params)
    for call in load(ROOT / "runs" / world_id / "journal.jsonl"):
        if call.op != "advance" or call.resp is None:
            continue
        for e in call.resp["events"]:
            if e["kind"] == "price_request" and e["request"]["arrivedAt"] >= params.start_minute and not declined(e["request"], params):
                learning.quoted.add(e["request"]["id"])
            learning.see(e)
    return [(0, params.price_mult)] + learning.history


def table(name: str, labels: list[str]) -> tuple[str, list[dict]]:
    r = json.loads((SWEEPS / f"{name}.json").read_text(encoding="utf-8"))
    out, summary = [], []
    for st, lab in zip(r["settings"], labels):
        rows = {x["seed"]: x for x in r["rows"] if x["setting"] == st}
        cells, tot, ranked, worst, won = [], 0, 0, 1.0, 0
        for s in r["seeds"]:
            sc = rows[s].get("score")
            if not sc:
                cells.append("<td>—</td>")
                continue
            ok = sc["onTimeShare"] >= 0.9
            tot += sc["marginCents"]; ranked += ok; worst = min(worst, sc["onTimeShare"]); won += sc["wonOrders"]
            cells.append(f'<td class="{"" if ok else "bad"}">{sc["onTimeShare"] * 100:.1f}%{" ✓" if ok else ""}<br><span class="sub">{eur(sc["marginCents"])} · {sc["wonOrders"]}</span></td>')
        summary.append({"label": lab, "setting": st, "total": tot, "ranked": ranked, "n": len(r["seeds"]), "worst": worst, "won": won, "rows": rows})
        out.append(f"<tr><th scope=row>{html.escape(lab)}</th>{''.join(cells)}<td>{ranked}/{len(r['seeds'])}</td><td>{worst * 100:.1f}%</td><td>{eur(tot)}</td></tr>")
    head = "".join(f"<th scope=col>{s}</th>" for s in r["seeds"])
    return (f'<div class="scroll"><table><thead><tr><th scope=col>Policy</th>{head}<th scope=col>Ranked</th><th scope=col>Worst week</th>'
            f'<th scope=col>Total margin</th></tr></thead><tbody>{"".join(out)}</tbody></table></div>'), summary


def multiples(arm: dict) -> str:
    """One small panel per world: the adaptive multiplier over the week (Mon to Sat)."""
    panels = []
    params = params_of(arm["setting"])
    for seed, row in arm["rows"].items():
        pts = path_of(row["worldId"], params)
        w, h, pad = 170, 90, 22
        x = lambda m: pad + (w - pad - 6) * min(m, 5 * 1440) / (5 * 1440)
        y = lambda v: 8 + (h - 30) * (1.9 - v) / 0.9
        d = "M" + " L".join(f"{x(m):.1f},{y(v):.1f}" for m, v in pts) + f" L{x(5 * 1440):.1f},{y(pts[-1][1]):.1f}"
        sc = row.get("score") or {}
        grid = "".join(f'<line x1="{pad}" x2="{w - 6}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/><text x="{pad - 3}" y="{y(v) + 3:.1f}" class="tick" text-anchor="end">{v:g}</text>' for v in (1.0, 1.5))
        days = "".join(f'<text x="{x(dd * 1440 + 720):.1f}" y="{h - 6}" class="tick" text-anchor="middle">{"MTWTF"[dd]}</text>' for dd in range(5))
        panels.append(f'<figure class="sm"><figcaption>{html.escape(seed)} · {eur(sc.get("marginCents"))} · {sc.get("onTimeShare", 0) * 100:.0f}%</figcaption>'
                      f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="multiplier over the week, {html.escape(seed)}">{grid}{days}'
                      f'<path d="{d}" fill="none" stroke="var(--s1)" stroke-width="2"/></svg></figure>')
    return f'<div class="smgrid">{"".join(panels)}</div>'


def page() -> str:
    full, s_full = table("adapt1", [LABELS[i] for i in range(5)])
    thu, s_thu = table("adapt1_thu", [LABELS[0], LABELS[2]])
    a, c = s_full[0], s_full[2]
    banner = status("good", f"Adopted C: ranked {c['ranked']}/{c['n']} full weeks and {s_thu[1]['ranked']}/{s_thu[1]['n']} Thursday-start weeks; "
                            f"{eur(c['total'] - a['total'])} over 8 weeks and {eur(s_thu[1]['total'] - s_thu[0]['total'])} over 4 short weeks against the fixed price")
    tile = lambda label, value, sub: f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'
    tiles = "".join([
        tile("Margin per full L8 week (C)", eur(c["total"] // c["n"]), f"mean of {c['n']} weeks incl. the 4 hardest seeds; fixed price {eur(a['total'] // a['n'])}"),
        tile("Worst week on time (C)", f"{c['worst'] * 100:.1f}%", f"fixed price {a['worst'] * 100:.1f}%; the gate is 90%"),
        tile("Thursday-start weeks (C)", eur(s_thu[1]["total"] // s_thu[1]["n"]), f"per week, like the test final; fixed price {eur(s_thu[0]['total'] // s_thu[0]['n'])}"),
        tile("Test final 1 (fixed 1.5×)", "12 orders", "won 2.9% of requests; the top ranked teams won 135-167. The reason for this step"),
    ])
    body = f"""
<h1>Step 5 · A price that adapts to each world</h1>
<p>In test final 1 the desk answered every request in time but won only 12 orders: a fixed 1.5× list was too dear for that world, while the competitor's level differs from world to world (1.26-1.54× list). The adaptive price starts at 1.5× and steers the multiplier so that about 40% of real quotes win. It moves at most 4% per update, only every 30 world minutes and only after 5 new outcomes (so a bulk order cannot swing it and it does not drift overnight). It never quotes below the request's typical fee × 1.15, and it pushes the price up instead when more than 80 orders were won in the last 24 hours. It is a pure function of events, so the desk rebuilds it exactly after a restart.</p>
<div class="banner">{banner}</div>
<div class="tiles">{tiles}</div>
<h2>Eight full L8 weeks, the same for every policy</h2>
<p class="note">dev-1, dev-3, hold-2 and hold-5 are the weeks that were hardest before. Each cell: on-time share (✓ = ranked), margin, orders won. The server's canary was clean.</p>
{full}
<h2>Four weeks that start on Thursday, like the test final</h2>
{thu}
<h2>The multiplier in each world (policy C)</h2>
<p>Each world settles at its own price: where the competitor is dear the desk stays high, where it is cheap it walks down toward list.</p>
<div class="card">{multiples(c)}</div>
<h2>What was decided</h2>
<ul>
<li><b>C is adopted</b> for test final 2 and the final: ranked everywhere, the best worst week, and the most margin among the policies ranked on every week.</li>
<li><b>E is rejected</b>: a looser slack filter earns more but misses the gate on hold-5 (87.8%).</li>
<li><b>The trust markup is a trade, not a gain</b>: at the 30% target it cost margin (B {eur(s_full[1]['total'])} with it, D {eur(s_full[3]['total'])} without) but raised the worst week ({s_full[1]['worst'] * 100:.1f}% against {s_full[3]['worst'] * 100:.1f}%). It is kept in C for that buffer; C without it was not tested.</li>
<li><b>The earlier hold-out failures were artefacts</b>: hold-2 and hold-5 are ranked under the fixed price too (94.2%, 93.3%); they had failed only while the kit client sent requests twice on a flaky network.</li>
</ul>
<p class="note">Built by <code>python -m tools.proof_adapt</code> from evidence/sweeps/adapt1.json and adapt1_thu.json; the multiplier paths are replayed from runs/*/journal.jsonl.</p>
"""
    head = G0_TEMPLATE.split("<main>")[0].replace("Spread G0 proof", "Spread adaptive price proof").replace(
        ".routes{{", ".sub{{color:var(--muted);font-size:11px}}.smgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}}"
                     ".sm{{margin:0}}.sm figcaption{{font-size:12px;color:var(--ink2);margin-bottom:2px}}.routes{{")
    return head.format() + "<main>" + body + "</main>" + G0_TEMPLATE.split("</main>")[1].format()


def main() -> None:
    OUT.write_text(page(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
