"""The proof page must render every outcome (extra lines, mismatches) and never let file text become markup."""
import html
import re
from pathlib import Path

from tools.g0 import compare_transcript, parse_transcript
from tools.proof_g0 import l8_table, margin_chart

ROOT = Path(__file__).resolve().parents[1]
HANDBOOK_L8 = (ROOT / "expected" / "handbook_L8_spread-1.txt").read_text(encoding="utf-8")


def test_chart_and_table_survive_an_extra_line():
    extra = HANDBOOK_L8 + "\nEnd        margin €      -1.00  revenue €       1.00     1 orders    1.0% on time   0.0% not delivered\n"
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(extra))
    assert margin_chart(rows).startswith("<svg")
    table = l8_table(rows)
    assert "extra: End" in table and "−€1.00" in table


def test_tooltip_markup_stays_escaped_after_the_attribute_is_decoded():
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(HANDBOOK_L8))
    rows[0] = {**rows[0], "label": "<img src=x onerror=alert(1)>"}
    svg = margin_chart(rows)
    tips = [html.unescape(t) for t in re.findall(r'data-tip="([^"]*)"', svg)]  # what dataset.tip holds in the browser
    assert "<img" not in tips[0] and "&lt;img" in tips[0]


def test_table_marks_a_relabelled_line():
    relabelled = HANDBOOK_L8.replace("Sunday ", "Sundae ")
    table = l8_table(compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(relabelled)))
    assert "(ours: Sundae)" in table
