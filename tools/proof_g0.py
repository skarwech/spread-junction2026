"""Builds proof/g0.html from the saved evidence: evidence/g0/*.txt, evidence/g0/result.json and data/board/*.json.

    python -m tools.proof_g0

Every number on the page is read from those files; nothing is typed in by hand.
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone
from typing import Optional

from tools.g0 import EVIDENCE, ROOT, SEED, report

OUT = ROOT / "proof" / "g0.html"
BOARD = ROOT / "data" / "board"
HOUSE = {"house-strong": "House best", "house-starter": "House starter"}


def eur(cents: Optional[int], signed: bool = True) -> str:
    if cents is None:
        return "—"
    sign = "−" if cents < 0 else ("+" if signed and cents > 0 else "")
    return f"{sign}€{abs(cents) / 100:,.2f}"


def eur_k(cents: Optional[float]) -> str:
    if cents is None:
        return "—"
    v = cents / 100
    return "0" if v == 0 else f"{'−' if v < 0 else ''}€{abs(v) / 1000:,.0f}K"


def pct(share: Optional[float]) -> str:
    return "—" if share is None else f"{share * 100:.1f}%"


def status(kind: str, text: str) -> str:
    icon = {"good": "✓", "critical": "✕", "neutral": "○"}[kind]
    return f'<span class="chip chip-{kind}"><span aria-hidden="true">{icon}</span> {html.escape(text)}</span>'


CHECK_NAMES = {"exit": "clean exit", "practice": "practice world", "level": "asked level", "verdict": "ranked verdict"}


def level_status(entry: dict) -> str:
    if not entry["ran"]:
        exited = entry.get("exit")
        return status("neutral", "Not run") if exited is None else status("critical", f"Run failed (exit {exited})")
    if entry["match"]:
        return status("good", "Matches to the cent")
    failed = [CHECK_NAMES[k] for k, ok in entry["checks"].items() if not ok]
    return status("critical", "Does not match" + (f": {', '.join(failed)}" if failed else ""))


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    span = hi - lo or 1
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    return [start + i * step for i in range(int(math.ceil((hi - start) / step)) + 1)]


def margin_chart(rows: list[dict]) -> str:
    """L8 margin after each day: handbook line (series 1) and our run as dots (series 2).
    Extra lines in our run have no handbook point; the table lists them."""
    rows = [r for r in rows if r["expected"] is not None]
    labels = [r["label"] for r in rows]
    want = [r["expected"]["margin_cents"] for r in rows]
    got = [r["actual"]["margin_cents"] if r["actual"] else None for r in rows]
    values = want + [g for g in got if g is not None]
    ticks = nice_ticks(min(values + [0]), max(values + [0]))
    w, h, left, right, top, bottom = 720, 300, 64, 16, 16, 40
    pw, ph = w - left - right, h - top - bottom
    x = lambda i: left + pw * (i + 0.5) / len(rows)
    y = lambda v: top + ph * (ticks[-1] - v) / (ticks[-1] - ticks[0])
    grid = "".join(
        f'<line x1="{left}" x2="{w - right}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="{"axis" if t == 0 else "grid"}"/>'
        f'<text x="{left - 8}" y="{y(t) + 4:.1f}" class="tick" text-anchor="end">{eur_k(t)}</text>' for t in ticks)
    xlabels = "".join(f'<text x="{x(i):.1f}" y="{h - 14}" class="tick" text-anchor="middle">{"Mon²" if (l == "Monday" and i > 6) else "Tue²" if (l == "Tuesday" and i > 6) else l[:3]}</text>'
                      for i, l in enumerate(labels))
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(want))
    dots1 = "".join(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" class="dot1"/>' for i, v in enumerate(want))
    dots = "".join(f'<circle cx="{x(i):.1f}" cy="{y(g):.1f}" r="5" class="dot2"/>' for i, g in enumerate(got) if g is not None)
    def tip(i: int) -> str:
        # Escaped twice on purpose: once for the tooltip's innerHTML, once for the attribute.
        inner = f"<b>{html.escape(labels[i])}</b><br>Handbook {eur(want[i])}<br>Our run {eur(got[i])}"
        return html.escape(inner + ("" if got[i] is None else f"<br>Difference {eur(got[i] - want[i])}"))
    hits = "".join(
        f'<rect x="{x(i) - pw / len(rows) / 2:.1f}" y="{top}" width="{pw / len(rows):.1f}" height="{ph}" class="hit" data-x="{x(i):.1f}" '
        f'data-tip="{tip(i)}"/>' for i in range(len(rows)))
    return (f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Level 8 margin after each day, handbook versus our run">'
            f'{grid}{xlabels}<line class="crosshair" x1="0" x2="0" y1="{top}" y2="{top + ph}" visibility="hidden"/>'
            f'<path d="{path}" class="line1"/>{dots1}{dots}{hits}</svg>')


def l8_table(rows: list[dict]) -> str:
    def cell(r: dict, f: str, fmt) -> str:
        a, b = r["fields"].get(f, (None, None))
        cls = "" if a == b else ' class="bad"'
        return f"<td{cls}>{fmt(a)}</td><td{cls}>{fmt(b)}</td>"
    tenth = lambda v: "—" if v is None else f"{v / 10:.1f}%"
    num = lambda v: "—" if v is None else f"{v:,}"
    def label(r: dict) -> str:
        if r["expected"] is None:
            return f'<span class="bad-text">extra: {html.escape(r["label"])}</span>'
        if r["actual_label"] not in (None, r["label"]):
            return f'{html.escape(r["label"])} <span class="bad-text">(ours: {html.escape(r["actual_label"])})</span>'
        return html.escape(r["label"])
    body = "".join(
        f"<tr><th scope=row>{label(r)}</th>{cell(r, 'margin_cents', eur)}{cell(r, 'revenue_cents', lambda v: eur(v, False))}"
        f"{cell(r, 'orders', num)}{cell(r, 'on_time_permille', tenth)}{cell(r, 'undelivered_permille', tenth)}"
        f"<td>{'✓' if r['match'] else '✕' if r['actual'] else '○'}</td></tr>" for r in rows)
    head = "".join(f'<th colspan=2 scope=colgroup>{h}</th>' for h in ("Margin", "Revenue", "Orders", "On time", "Not delivered"))
    sub = "<th scope=col>Handbook</th><th scope=col>Ours</th>" * 5
    return (f'<div class="scroll"><table><thead><tr><th rowspan=2 scope=col>Day</th>{head}<th rowspan=2 scope=col>Match</th></tr>'
            f"<tr>{sub}</tr></thead><tbody>{body}</tbody></table></div>")


def board_section() -> str:
    parts = []
    for level in (8, 7, 6):
        path = BOARD / f"level{level}.json"
        if not path.exists():
            continue
        board = json.loads(path.read_text(encoding="utf-8"))
        fetched = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone().strftime("%a %H:%M %Z")
        season = board["current"]
        played = [t for t in season["teams"] if t["played"] > 0]
        played.sort(key=lambda t: (t["marginCents"] is None, -(t["marginCents"] or 0)))
        rows = "".join(
            f"<tr{' class=house' if t['team'] in HOUSE else ''}><th scope=row>{html.escape(str(HOUSE.get(t['team']) or t.get('name') or t['team']))}</th>"
            f"<td>{int(t['played'])}</td><td>{eur(t['marginCents'])}</td><td>{pct(t['onTimeShare'])}</td>"
            f"<td>{'yes' if t['ranked'] else 'no'}</td><td>{', '.join(str(int(r['wonOrders'])) for r in t['runs'])}</td>"
            f"<td class=runs>{' · '.join(eur_k(r.get('marginCents')) for r in t['runs'])}</td></tr>" for t in played)
        parts.append(
            f"<h3>Level {level} · round {int(season['season'])} “{html.escape(str(season['name']))}” · {len(played)} of {len(season['teams'])} teams have played</h3>"
            f'<div class="scroll"><table><thead><tr><th scope=col>Team</th><th scope=col>Runs</th><th scope=col>Total margin</th>'
            f"<th scope=col>On time</th><th scope=col>Ranked</th><th scope=col>Won orders per run</th><th scope=col>Margin per run</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div><p class=note>Public board, fetched {fetched}.</p>")
    return "".join(parts)


def transcripts() -> str:
    out = []
    for name in ("starter_L8", "starter_L7", "starter_L6", "counted_L8"):
        p = EVIDENCE / f"{name}_{SEED}.txt"
        text = p.read_text(encoding="utf-8") if p.exists() else "(not run yet)"
        out.append(f"<details><summary>{name}_{SEED}.txt</summary><pre>{html.escape(text)}</pre></details>")
    return "".join(out)


def page(result: dict) -> str:
    lv = result["levels"]
    attempted = any(lv[k]["ran"] or lv[k].get("exit") is not None for k in ("8", "7", "6"))
    banner = (status("good", "G0 passed: the starter reproduces the handbook to the cent at L8, L7 and L6") if result["g0_pass"]
              else status("critical", "G0 not passed: see the levels below") if attempted
              else status("neutral", "G0 not run yet"))
    tiles = "".join(
        f'<div class="tile"><div class="label">Level {k} · end margin</div><div class="value">{eur(lv[k]["end"]["actual"])}</div>'
        f'<div class="sub">Handbook {eur(lv[k]["end"]["expected"])}</div>{level_status(lv[k])}'
        f'<div class="sub">{"world " + html.escape(lv[k]["world_id"] or "") + " · " if lv[k]["world_id"] else ""}{str(lv[k].get("elapsed_s", "")) + " s" if lv[k].get("elapsed_s") else ""}</div></div>'
        for k in ("8", "7", "6"))
    c = result["counted"]
    req = (f'<div class="tile"><div class="label">Advance steps, L8 week</div><div class="value">{c["advance_requests"] or 0:,}</div>'
           f'<div class="sub">API.md says {c["expected_requests"]:,}</div>'
           f'{status("good" if c["ok"] else "critical", "Counted run OK" if c["ok"] else "Counted run not OK")}'
           f'<div class="sub">All requests {c["requests"]:,} (incl. separate action posts) · exit {c.get("exit", "—")} · '
           f'same week as the CLI run: {"yes" if c["same_as_cli"] else "no"}</div></div>') if c["requests"] else ""
    routes = "".join(f"<li><code>{html.escape(k)}</code> {v:,}</li>" for k, v in sorted(c["by_route"].items(), key=lambda kv: -kv[1]))
    rows = lv["8"]["rows"]
    chart = margin_chart(rows) if rows else '<p class="empty">The chart appears once the level 8 run exists.</p>'
    table = l8_table(rows) if rows else ""
    return TEMPLATE.format(banner=banner, tiles=tiles + req, chart=chart, table=table, routes=f"<ul class=routes>{routes}</ul>" if routes else "",
                           board=board_section(), transcripts=transcripts(), seed=SEED)


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spread G0 proof</title><style>
:root{{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--good:#0ca30c;--goodtext:#006300;--critical:#d03b3b;--bad-bg:#fbe9e9;--house:#f0efec}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--goodtext:#0ca30c;--bad-bg:#3a1d1d;--house:#262624}}}}
:root[data-theme="dark"]{{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--goodtext:#0ca30c;--bad-bg:#3a1d1d;--house:#262624}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 64px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:17px;margin:32px 0 8px}}h3{{font-size:14px;margin:20px 0 6px;color:var(--ink2)}}
p{{margin:4px 0;color:var(--ink2)}}.note{{font-size:12px;color:var(--muted)}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;margin-top:8px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px}}
.tile{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px}}.label{{font-size:13px;color:var(--ink2)}}
.value{{font-size:26px;font-weight:600;margin:2px 0}}.sub{{font-size:12px;color:var(--muted);margin:4px 0}}
.chip{{display:inline-flex;gap:6px;align-items:center;font-size:13px;font-weight:600;padding:3px 10px;border-radius:999px;border:1px solid var(--border);margin-top:4px}}
.chip-good{{color:var(--goodtext)}}.chip-critical{{color:var(--critical)}}.chip-neutral{{color:var(--ink2)}}.banner{{margin-top:12px}}.banner .chip{{font-size:15px;padding:6px 14px}}
.chart{{width:100%;height:auto;display:block}}.grid{{stroke:var(--grid);stroke-width:1}}.axis{{stroke:var(--axis);stroke-width:1}}.tick{{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}}
.line1{{fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}}.dot1{{fill:var(--s1);stroke:var(--surface);stroke-width:2}}
.dot2{{fill:var(--s2);stroke:var(--surface);stroke-width:2}}.hit{{fill:transparent}}.crosshair{{stroke:var(--axis);stroke-width:1}}
.legend{{display:flex;gap:16px;font-size:13px;color:var(--ink2);margin-bottom:6px}}.key{{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:6px}}
.keydot{{display:inline-block;width:10px;height:10px;border-radius:50%;vertical-align:middle;margin-right:6px}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums;background:var(--surface)}}
th,td{{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}}th[scope=row],thead th:first-child{{text-align:left}}
thead th{{color:var(--ink2);font-weight:600}}.bad-text{{color:var(--critical);font-weight:600}}td.bad{{background:var(--bad-bg);color:var(--critical);font-weight:600}}tr.house{{background:var(--house)}}td.runs{{color:var(--ink2)}}
#tip{{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 4px 16px rgba(0,0,0,.12);display:none;z-index:5}}
details{{margin-top:8px}}summary{{cursor:pointer;color:var(--ink2)}}pre{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;overflow-x:auto;font-size:12px}}
.routes{{columns:2;font-size:12px;color:var(--ink2)}}.empty{{color:var(--muted)}}
</style></head><body><main>
<h1>G0 · The kit starter on seed {seed}</h1>
<p>Gate G0 checks that our setup plays the same week as the handbook. The unmodified <code>spread-starter</code> runs at levels 8, 7 and 6 on seed <code>{seed}</code>. At level 8 every printed line (10 lines × 5 fields) is compared to the handbook's transcript to the cent; at levels 7 and 6 the handbook publishes only the end margin, so that is what is compared. Each level must also exit cleanly, be a practice world (never a ranking run) at the asked level, and at level 8 print the same ranked verdict. A separate level 8 run counts API requests; it only wraps the client to count, so its week must be identical.</p>
<div class="banner">{banner}</div>
<div class="tiles">{tiles}</div>
<h2>Level 8 margin after each day</h2>
<div class="card"><div class="legend"><span><span class="key" style="background:var(--s1)"></span>Handbook (HANDBOOK.md, lines 40–49)</span><span><span class="keydot" style="background:var(--s2)"></span>Our run</span></div>{chart}
<p class="note">² = the last Monday and Tuesday of the world. Revenue counts at delivery, so the daily lines lag the orders.</p></div>
{table}
<h2>Requests by route (counted L8 run)</h2>{routes}
<h2>Baseline: the public practice board (experiment E3)</h2>
<p>The targets to beat. House best is the organisers' best system and House starter is the kit starter; both play every ranking round.</p>
{board}
<h2>Raw output</h2><p class="note">The page is built from these files by <code>python -m tools.proof_g0</code>.</p>{transcripts}
</main><div id="tip"></div><script>
const tip=document.getElementById('tip');const cross=document.querySelector('.crosshair');
document.querySelectorAll('[data-tip]').forEach(el=>{{
 const show=e=>{{tip.innerHTML=el.dataset.tip;tip.style.display='block';tip.style.left=Math.min(e.clientX+14,innerWidth-200)+'px';tip.style.top=(e.clientY+14)+'px';
  if(cross&&el.dataset.x){{cross.setAttribute('x1',el.dataset.x);cross.setAttribute('x2',el.dataset.x);cross.setAttribute('visibility','visible');}}}};
 el.addEventListener('mouseover',show);el.addEventListener('mousemove',show);
 el.addEventListener('mouseout',()=>{{tip.style.display='none';if(cross)cross.setAttribute('visibility','hidden');}});
}});
</script></body></html>"""


def main() -> None:
    result = report()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page(result), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}; G0 {'PASS' if result['g0_pass'] else 'not passed'}")


if __name__ == "__main__":
    main()
