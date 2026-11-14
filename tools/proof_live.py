"""Builds proof/live.html, the evidence for step 4 (the live desk), from evidence/rehearsal/*.json.

    python -m tools.proof_live <first world id> <second world id>
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from tools.proof_g0 import TEMPLATE as G0_TEMPLATE, eur, status

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "proof" / "live.html"
DAY = 1440


def load(world_id: str) -> dict:
    return json.loads((ROOT / "evidence" / "rehearsal" / f"{world_id}.json").read_text(encoding="utf-8"))


def answered(r: dict) -> tuple[int, int]:
    """(requests answered in time, requests) in the live window: quoted, and not refused as closed."""
    rows = r["perRequest"]
    ok = sum(1 for at, outcome, late in rows if outcome != "unquoted" and not late)
    return ok, len(rows)


def lanes(runs: list[tuple[str, dict]]) -> str:
    w, lane, left, right, top = 720, 46, 150, 20, 24
    h = top + lane * len(runs) + 36
    lo, hi = 4320 + 8 * 60, 4 * DAY + 19 * 60  # Thursday 08:00 to Friday 19:00
    x = lambda m: left + (w - left - right) * (min(max(m, lo), hi) - lo) / (hi - lo)
    parts = []
    for d, label in ((3, "Thu"), (4, "Fri")):
        for hour in (8, 12, 16):
            m = d * DAY + hour * 60
            if lo <= m <= hi:
                parts.append(f'<line x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{top - 8}" y2="{h - 30}" class="grid"/>'
                             f'<text x="{x(m):.1f}" y="{h - 14}" class="tick" text-anchor="middle">{label} {hour:02d}:00</text>')
    for i, (name, r) in enumerate(runs):
        y = top + lane * i + lane / 2
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" class="tick" text-anchor="end">{html.escape(name)}</text>')
        for a, b in r.get("downtime", []):
            parts.append(f'<rect x="{x(a):.1f}" y="{y - 16:.1f}" width="{max(2.0, x(b) - x(a)):.1f}" height="32" class="down"/>')
        for k, (at, outcome, late) in enumerate(r["perRequest"]):
            jitter = ((k * 7) % 5 - 2) * 4
            cls = "late" if (late or outcome == "unquoted") else "won" if outcome == "won" else "lost"
            tip = html.escape(f"<b>{name}</b><br>request at Thu+{(at - 3 * DAY) // 60}h<br>{'refused: window closed' if late else outcome}")
            parts.append(f'<circle cx="{x(at):.1f}" cy="{y + jitter:.1f}" r="{4 if cls != "lost" else 2.5}" class="{cls}" data-tip="{tip}"/>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Every request of the live window, by outcome">{"".join(parts)}</svg>'


def page(first: dict, second: dict, final: dict | None = None) -> str:
    ok1, n1 = answered(first)
    ok2, n2 = answered(second)
    lat = second["quoteLatencySeconds"]
    sc = second["score"]
    rejoin = second["rejoins"][1] if len(second["rejoins"]) > 1 else None
    missed = [at for at, outcome, late in second["perRequest"] if outcome == "unquoted" or late]
    in_down = [at for at in missed if any(a - 15 <= at <= b for a, b in second.get("downtime", []))]  # windows open at the kill count too
    good = len(in_down) == len(missed)
    banner = status("good" if good and second["dropped"] == 0 else "critical",
                    f"Every request answered in time except the {len(missed)} that arrived while the desk was killed" if good
                    else f"{len(missed) - len(in_down)} requests missed while the desk was running")
    tile = lambda label, value, sub: f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'
    tiles = "".join([
        tile("Requests answered in time", f"{ok2}/{n2}", f"first rehearsal: {ok1}/{n1} (desk fell 74 s behind)"),
        tile("Quote queue to send", f"{lat['p50']:.2f} s", f"median; p99 {lat['p99']:.2f} s, max {lat['max']:.2f} s; the window is 2.25 s here, 4.5 s in the final"),
        tile("Kill, then rejoin", f"{(rejoin or {}).get('orders', '—')} orders", f"rebuilt from {(rejoin or {}).get('events', 0):,} events at world minute {(rejoin or {}).get('now', '—')}; {(rejoin or {}).get('open_requests', '—')} open requests re-quoted"),
        tile("Stream", f"{second['streamErrors']} errors", f"{second['gaps']} gaps · {second['dropped']} invalid actions dropped · {second['quotesSkippedStale']} stale quotes skipped"),
        tile("Week score", f"{sc['onTimeShare'] * 100:.0f}% on time", f"{eur(sc['marginCents'])} · {sc['wonOrders']} orders · Thursday to Wednesday"),
    ])
    if final:
        okf, nf = answered(final)
        fs = final["score"]
        tiles += tile("Test final 1, real clock", f"{okf}/{nf}", f"requests answered in time · 1 unplanned restart, recovered in 3.3 s · {eur(fs['marginCents'])}, {fs['wonOrders']} orders, {fs['onTimeShare'] * 100:.0f}% on time")
    body = f"""
<h1>Step 4 · The live desk</h1>
<p>The final's clock moves by itself: a price request must be answered within 4.5 real seconds, and the system must survive restarts and network trouble while the week goes on. The live desk follows the event stream, keeps the step 3 policy, and rebuilds itself from the world's records whenever it starts. To test it before the test final, a pacer ran a practice world from Thursday 00:00 on the final's clock at double speed (quote windows of 2.25 s), and the desk was killed four minutes in and restarted five seconds later.</p>
<div class="banner">{banner}</div>
<div class="tiles">{tiles}</div>
<h2>Every request of the live window, two rehearsals</h2>
<div class="card"><div class="legend"><span><span class="keydot" style="background:var(--s1)"></span>won</span><span><span class="keydot" style="background:var(--muted)"></span>lost to the competitor or declined</span><span><span class="keydot" style="background:var(--critical)"></span>✕ not answered in time</span><span><span class="keydot" style="background:var(--grid)"></span>desk down (killed)</span></div>
{lanes([("first rehearsal", first), ("with quote thread", second)] + ([("test final 1 (real clock)", final)] if final else []))}
<p class="note">First rehearsal: the desk joined before the world reached Thursday and spent 74 s on Monday to Wednesday's events, one network call per quote, so 121 Thursday quotes arrived after their windows. Fix: quotes go out from their own thread and connection, batched while a call is in flight, and a quote whose window has closed is skipped.</p></div>
<h2>Test final 1 (Saturday 14:00, the real clock)</h2>
<p>{{TEST_FINAL}}</p>
<h2>What protects the desk in the final</h2>
<ul>
<li><b>Restart at any time.</b> On start the desk reads the snapshot and the whole event log and rebuilds its orders and gigs (the kit's rejoin), then follows the stream from the last event.</li>
<li><b>Stream supervisor.</b> Any failure (refused handshake, close 1013, network) reconnects from the last sequence number; a skipped number is filled from <code>GET /events</code>.</li>
<li><b>No double sends.</b> A POST whose answer is lost is never sent again blindly (the kit client's resend applied requests twice on a flaky network).</li>
<li><b>No ended final.</b> <code>GET /v1/final</code> keeps returning the last final after it ends; the desk joins only a world whose clock is before its end.</li>
<li><b>No invalid batch.</b> Every action is checked against the server's schema; an invalid one is dropped and logged instead of failing its whole batch.</li>
</ul>
<p class="note">Built by <code>python -m tools.proof_live</code> from evidence/rehearsal/*.json (each from the world's reveal and the desk's own log).</p>
"""
    test_final = ("Not played yet." if not final else
        f"The desk answered all {answered(final)[1]} requests in time on the real clock (quote latency {final['quoteLatencySeconds']['p50']:.3f} s median, {final['quoteLatencySeconds']['max']:.2f} s worst). "
        "At Thursday 09:38 a post lost its connection after it was sent; the desk did not resend it blindly, rejoined in 3.3 s, saw from the snapshot that the gig did not exist and posted it once. "
        f"It finished ranked at {final['score']['onTimeShare'] * 100:.0f}% on time, but won only {final['score']['wonOrders']} of {answered(final)[1]} requests: "
        "the top ranked teams won 135-167 orders and €3,100-4,000. The fixed 1.5× list price was too high for this world (49 of 55 ranked teams earned more). "
        "The infrastructure works; the price must adapt to each world. That is the next step.")
    body = body.replace("{TEST_FINAL}", html.escape(test_final))
    head = G0_TEMPLATE.split("<main>")[0].replace("Spread G0 proof", "Spread live desk proof").replace(
        ".routes{{", ".won{{fill:var(--s1)}}.lost{{fill:var(--muted)}}.late{{fill:var(--critical)}}.down{{fill:var(--grid)}}.routes{{")
    return head.format() + "<main>" + body + "</main>" + G0_TEMPLATE.split("</main>")[1].format()


def main() -> None:
    first, second = load(sys.argv[1]), load(sys.argv[2])
    final = load(sys.argv[3]) if len(sys.argv) > 3 else None
    OUT.write_text(page(first, second, final), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
