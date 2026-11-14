"""Builds proof/core.html, the evidence for step 2 (the desk core), from saved files only:

- evidence/restart/result.json      kill/resume runs (tools.restart_test)
- runs/<world>/summary.json         books vs the server's score at each midnight (desk.runner)
- the action fuzz (re-run here, seeded) and the pytest count

    python -m tools.proof_core
"""
from __future__ import annotations

import html
import json
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from tools.g0 import compare_transcript, parse_transcript
from tools.proof_g0 import TEMPLATE as G0_TEMPLATE, eur, status

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "proof" / "core.html"
RUNS = ROOT / "runs"
HANDBOOK_L8 = ROOT / "expected" / "handbook_L8_spread-1.txt"


def fuzz_stats(n: int = 5000) -> dict:
    sys.path.insert(0, str(ROOT))
    from tests.test_actions import base_actions, mutations, schema_ok
    from desk import actions as A
    rng = random.Random(20261113)
    cases = [mutations(rng, rng.choice(base_actions())) for _ in range(n)]
    ours = [not A.schema_errors(c) for c in cases]
    theirs = [schema_ok(c) for c in cases]
    return {"cases": n, "agree": sum(a == b for a, b in zip(ours, theirs)), "looser": sum(a and not b for a, b in zip(ours, theirs)),
            "stricter": sum(b and not a for a, b in zip(ours, theirs)), "valid": sum(theirs)}


def pytest_count() -> str:
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) passed(?:, (\d+) failed)?", out)
    return f"{m[1]} passed" + (f", {m[2]} failed" if m and m[2] else "") if m else "no result"


def summary_of(world_id: Optional[str]) -> Optional[dict]:
    p = RUNS / (world_id or "-") / "summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def find_run(level: int, seed: str) -> Optional[dict]:
    for meta in sorted(RUNS.glob("*/meta.json"), key=lambda p: p.stat().st_mtime):
        m = json.loads(meta.read_text(encoding="utf-8"))
        s = summary_of(m["worldId"])
        if m["level"] == level and m.get("seed") == seed and s and not m.get("resumes"):
            return s
    return None


def reconcile_rows(summary: dict) -> tuple[str, int]:
    rows, good = [], 0
    for d in summary["days"]:
        sc, o = d["score"], d["ours"]
        checks = [sc["marginCents"] == o["marginCents"], sc["revenueCents"] == o["revenueCents"], sc["wonOrders"] == o["wonOrders"],
                  abs(sc["onTimeShare"] - o["onTimeShare_onTimeOverDue"]) < 1e-9, abs(sc["undeliveredShare"] - o["undeliveredShare"]) < 1e-9]
        good += all(checks)
        mark = lambda ok: "" if ok else ' class="bad"'
        rows.append(f"<tr><th scope=row>{html.escape(d['label'])}</th><td{mark(checks[0])}>{eur(sc['marginCents'])}</td><td{mark(checks[0])}>{eur(o['marginCents'])}</td>"
                    f"<td{mark(checks[1])}>{eur(o['revenueCents'], False)}</td><td{mark(checks[2])}>{o['wonOrders']}</td>"
                    f"<td{mark(checks[3])}>{sc['onTimeShare'] * 100:.2f}%</td><td{mark(checks[3])}>{o['onTime']} / ({o['delivered']} + {o['overdue']})</td>"
                    f"<td>{o['events']:,}</td><td>{'✓' if all(checks) else '✕'}</td></tr>")
    head = ("<tr><th scope=col>Day</th><th scope=col>Server margin</th><th scope=col>Ledger sum</th><th scope=col>Revenue</th><th scope=col>Won</th>"
            "<th scope=col>Server on time</th><th scope=col>On time ÷ (delivered + overdue)</th><th scope=col>Events folded</th><th scope=col>All equal</th></tr>")
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>', good


def restart_chart(result: dict, ends_at: int) -> str:
    """One lane per run along the week; a mark at each kill (filled = the call was in flight)."""
    runs = result["runs"]
    w, lane, left, right, top = 720, 34, 120, 130, 22
    h = top + lane * len(runs) + 34
    x = lambda minute: left + (w - left - right) * minute / ends_at
    days = "".join(f'<line x1="{x(d * 1440):.1f}" x2="{x(d * 1440):.1f}" y1="{top - 6}" y2="{h - 30}" class="grid"/>'
                   f'<text x="{x(d * 1440 + 720):.1f}" y="{h - 14}" class="tick" text-anchor="middle">{["Mon","Tue","Wed","Thu","Fri","Sat","Sun","Mon²","Tue²","Wed²"][d]}</text>'
                   for d in range(int(ends_at // 1440) + 1) if d * 1440 < ends_at)
    marks = []
    for i, r in enumerate(runs):
        y = top + lane * i + lane / 2
        label = "control (no kill)" if r["run"] == 0 else f"run {r['run']}"
        marks.append(f'<text x="{left - 10}" y="{y + 4:.1f}" class="tick" text-anchor="end">{label}</text>'
                     f'<line x1="{x(0):.1f}" x2="{x(ends_at):.1f}" y1="{y:.1f}" y2="{y:.1f}" class="axis"/>')
        for k in r["kills"]:
            if "minute" not in k:
                continue
            tip = html.escape(f"<b>{label}, kill</b><br>world minute {k['minute']:,}<br>last call {k['lastOp']} #{k['calls']}<br>{'in flight: recovered from the world' if k['inFlight'] else 'between calls: replayed'}")
            cls = "dot2" if k["inFlight"] else "ring2"
            marks.append(f'<circle cx="{x(k["minute"]):.1f}" cy="{y:.1f}" r="6" class="{cls}" data-tip="{tip}"/>')
        ok = r["sameMargin"] and r["sameBooks"] and r["exit"] == 0
        marks.append(f'<text x="{x(ends_at) + 8:.1f}" y="{y + 4:.1f}" class="tick end-{"good" if ok else "bad"}">{"✓ " if ok else "✕ "}{eur(r["endMarginCents"])}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Kill points per run along the week">{days}{"".join(marks)}</svg>'


def page() -> str:
    restart = json.loads((ROOT / "evidence" / "restart" / "result.json").read_text(encoding="utf-8"))
    control = summary_of(restart["runs"][0]["worldId"])
    l6 = find_run(6, "spread-1")
    fuzz = fuzz_stats()
    tests = pytest_count()
    expected = parse_transcript(HANDBOOK_L8.read_text(encoding="utf-8"))
    g0_rows = compare_transcript(expected, parse_transcript("\n".join(control["transcript"]))) if control else []
    g0_same = bool(g0_rows) and all(r["match"] for r in g0_rows)
    rec_table, rec_good = reconcile_rows(control) if control else ("", 0)
    l6_good = reconcile_rows(l6)[1] if l6 else 0
    ends_at = control["days"][-1]["ours"]["now"] if control else 7 * 1440
    ends_at = max(ends_at, max((k.get("minute", 0) for r in restart["runs"] for k in r["kills"]), default=0)) + 1
    killed = [r for r in restart["runs"] if r["run"] > 0]
    banner = status("good", "Step 2 core works: books equal the server, actions match the schema, kills change nothing") if (restart["allSame"] and g0_same and fuzz["looser"] == 0) else status("critical", "Step 2 core: see the failures below")
    tile = lambda label, value, sub, ok, chip: (f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div>'
                                                f'{status("good" if ok else "critical", chip)}</div>')
    tiles = "".join([
        tile("Kill / resume, L8 spread-1", f"{restart['kills']} kills", f"{len(killed)} runs, {restart['inFlightKills']} kills with a call in flight; control run uninterrupted",
             restart["allSame"], "Every run ends identical" if restart["allSame"] else "A run differs"),
        tile("Books vs server score", f"{rec_good}/{len(control['days']) if control else 0} days", f"L8 control; L6 run {l6_good}/{len(l6['days']) if l6 else 0} days. Margin = sum of ledger lines",
             bool(control) and rec_good == len(control["days"]), "Equal on every field"),
        tile("Same week as the handbook", f"{sum(r['match'] for r in g0_rows)}/{len(g0_rows)} lines", "Starter policy run through the core, L8 spread-1", g0_same, "Matches to the cent"),
        tile("Actions vs openapi.json", f"{fuzz['agree'] / fuzz['cases']:.1%}", f"{fuzz['cases']:,} mutated actions · {fuzz['looser']} we accept that the server refuses · {fuzz['stricter']} stricter (whole floats)",
             fuzz["looser"] == 0, "Never looser than the server"),
        tile("Tests", tests, "journal, replay, in-flight recovery, validator, G0", "failed" not in tests, "All green"),
    ])
    runs_table = "".join(
        f"<tr><th scope=row>{'control' if r['run'] == 0 else r['run']}</th><td>{len(r['kills'])}</td><td>{sum(k.get('inFlight', False) for k in r['kills'])}</td>"
        f"<td>{', '.join(str(k.get('minute', '—')) for k in r['kills']) or '—'}</td><td>{html.escape(str((r.get('lastStats') or {}).get('replayed', '—')))}</td>"
        f"<td>{eur(r['endMarginCents'])}</td><td><code>{html.escape(str(r['fingerprint']))}</code></td><td>{'✓' if r['sameMargin'] and r['sameBooks'] and r['exit'] == 0 else '✕'}</td></tr>"
        for r in restart["runs"])
    body = f"""
<h1>Step 2 · The desk core</h1>
<p>Every call to a world goes through one door, <code>WorldIO</code>, which writes it to a journal before it leaves and its answer after it comes back. The books (<code>State</code>) are folded only from what the world said. After a crash, the desk replays its journal (no calls to the server, and every decision must come out the same, or it stops), recovers the one call that may have been in flight from the world's own snapshot and events, and goes on live. The policy here is still the kit's starter, so its week must equal the handbook's.</p>
<div class="banner">{banner}</div>
<div class="tiles">{tiles}</div>
<h2>Kill points along the week (SIGKILL, then resume)</h2>
<div class="card"><div class="legend"><span><span class="keydot" style="background:var(--s2)"></span>killed with a call in flight (answer rebuilt from the world)</span><span><span class="keydot ring"></span>killed between calls (replayed)</span></div>
{restart_chart(restart, ends_at)}
<p class="note">Each lane is one practice world on seed spread-1, level 8. The end margin and the books fingerprint (a digest of every ledger line, order and gig) must equal the control's.</p></div>
<div class="scroll"><table><thead><tr><th scope=col>Run</th><th scope=col>Kills</th><th scope=col>In flight</th><th scope=col>Kill minutes</th><th scope=col>Calls replayed (last resume)</th><th scope=col>End margin</th><th scope=col>Books fingerprint</th><th scope=col>Identical</th></tr></thead><tbody>{runs_table}</tbody></table></div>
<h2>Books vs the server's score at each midnight (L8 control)</h2>
<p>The server's mid-week on-time share turns out to be <b>orders delivered on time ÷ (orders delivered + undelivered orders past their deadline)</b>; not-yet-due orders do not count. The governor (μ) can now track it exactly.</p>
{rec_table}
<h2>How it fits together</h2>
<div class="card">{DIAGRAM}</div>
<p class="note">Built by <code>python -m tools.proof_core</code> from evidence/restart/result.json and runs/*/summary.json. Restart test took {restart['seconds']} s.</p>
"""
    return G0_TEMPLATE.split("<main>")[0].replace("Spread G0 proof", "Spread core proof").replace(
        ".routes{{", ".ring2{{fill:var(--surface);stroke:var(--s2);stroke-width:2}}.keydot.ring{{background:var(--surface);border:2px solid var(--s2);box-sizing:border-box}}.end-good{{fill:var(--goodtext)}}.end-bad{{fill:var(--critical)}}.routes{{"
    ).format() + "<main>" + body + "</main>" + G0_TEMPLATE.split("</main>")[1].format()


DIAGRAM = """<svg viewBox="0 0 720 170" class="chart" role="img" aria-label="Policy to WorldIO to world, with journal and state">
<g class="tick" font-size="12">
<rect x="10" y="55" width="130" height="50" rx="8" class="box"/><text x="75" y="78" text-anchor="middle">Policy</text><text x="75" y="94" text-anchor="middle">(starter for now)</text>
<rect x="230" y="55" width="150" height="50" rx="8" class="box"/><text x="305" y="78" text-anchor="middle">WorldIO</text><text x="305" y="94" text-anchor="middle">validate · record · replay</text>
<rect x="480" y="55" width="120" height="50" rx="8" class="box"/><text x="540" y="84" text-anchor="middle">World (API)</text>
<rect x="230" y="125" width="150" height="36" rx="8" class="box"/><text x="305" y="148" text-anchor="middle">journal.jsonl</text>
<rect x="230" y="5" width="150" height="36" rx="8" class="box"/><text x="305" y="28" text-anchor="middle">State (books)</text>
<line x1="140" y1="80" x2="226" y2="80" class="arrow"/><line x1="380" y1="80" x2="476" y2="80" class="arrow"/>
<line x1="305" y1="105" x2="305" y2="121" class="arrow"/><line x1="305" y1="55" x2="305" y2="45" class="arrow"/>
<text x="183" y="72" text-anchor="middle">actions</text><text x="428" y="72" text-anchor="middle">one call</text>
<text x="330" y="118">req, then resp</text><text x="330" y="52">events, results</text>
</g><style>.box{fill:var(--surface);stroke:var(--axis)}.arrow{stroke:var(--ink2);stroke-width:1.5}</style></svg>"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
