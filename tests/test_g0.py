"""Gate G0: the starter's printed week is parsed exactly and compared to the cent."""
from pathlib import Path

import pytest

from tools.g0 import (
    DayLine, assess_level, compare_end, compare_transcript, counted_ok, load_env, money_cents, parse_transcript, starter_command,
)

ROOT = Path(__file__).resolve().parents[1]
HANDBOOK_L8 = (ROOT / "expected" / "handbook_L8_spread-1.txt").read_text()


def test_money_cents_handles_sign_commas_and_padding():
    assert money_cents("     -22.26") == -2226
    assert money_cents("-72,612.51") == -7261251
    assert money_cents("71,332.00") == 7133200
    assert money_cents("0.00") == 0


def test_parse_handbook_week_has_ten_lines_and_exact_values():
    parsed = parse_transcript(HANDBOOK_L8)
    assert parsed.world_id == "w320bfbbab4715dd4a6c2"
    assert parsed.verdict.startswith("Not ranked")
    assert [d.label for d in parsed.days] == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Monday", "Tuesday", "End",
    ]
    assert parsed.days[0] == DayLine("Monday", -2226, 172100, 213, 702, 0)
    assert parsed.days[-1] == DayLine("End", -7261251, 7133200, 949, 455, 13)


def test_identical_transcripts_match_on_every_field():
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(HANDBOOK_L8))
    assert len(rows) == 10
    assert all(r["match"] for r in rows)


def test_one_cent_off_is_a_mismatch_on_that_line_only():
    tweaked = HANDBOOK_L8.replace("-14,714.24", "-14,714.25")
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(tweaked))
    assert [r["match"] for r in rows].count(False) == 1
    assert rows[3]["label"] == "Thursday" and rows[3]["fields"]["margin_cents"] == (-1471424, -1471425)


def test_missing_lines_are_mismatches_not_skipped():
    short = "\n".join(HANDBOOK_L8.splitlines()[:4])
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(short))
    assert len(rows) == 10
    assert sum(r["match"] for r in rows) == 3
    assert rows[-1]["actual"] is None


def test_compare_end_uses_end_line_margin():
    parsed = parse_transcript(HANDBOOK_L8)
    assert compare_end(-7261251, parsed) == {"expected": -7261251, "actual": -7261251, "match": True}
    assert compare_end(-117251, parsed)["match"] is False
    assert compare_end(-117251, None) == {"expected": -117251, "actual": None, "match": False}


def test_load_env_reads_pairs_and_ignores_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# team settings\nSPREAD_URL=https://x.test\nSPREAD_KEY=\nOTHER = 'quoted value'\n")
    assert load_env(env) == {"SPREAD_URL": "https://x.test", "SPREAD_KEY": "", "OTHER": "quoted value"}


def test_load_env_missing_file_is_empty(tmp_path):
    assert load_env(tmp_path / "nope.env") == {}


@pytest.mark.parametrize("line", [
    "", "random text", "End margin € abc",
    # a format drift must become a missing line (a mismatch), never a silently truncated value
    "Monday     margin €     -22.26  revenue €   1,721.00   213 orders   70.29% on time   0.0% not delivered",
    "Monday     margin €     -22.2  revenue €   1,721.00   213 orders   70.2% on time   0.0% not delivered",
])
def test_non_score_lines_are_ignored(line):
    assert parse_transcript(line).days == ()


def test_world_line_kind_and_level_are_parsed():
    assert parse_transcript(HANDBOOK_L8).kind == "Practice world"
    assert parse_transcript(HANDBOOK_L8).level == 8
    ranking = parse_transcript("Ranking run wabc123, level 8. Ctrl-C ...")
    assert (ranking.kind, ranking.world_id, ranking.level) == ("Ranking run", "wabc123", 8)


def test_an_extra_line_is_a_mismatch_that_keeps_its_values():
    extra = HANDBOOK_L8.replace("Not ranked", "End        margin €      -1.00  revenue €       1.00     1 orders    1.0% on time   0.0% not delivered\nNot ranked")
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(extra))
    assert len(rows) == 11 and rows[-1]["match"] is False
    assert rows[-1]["expected"] is None
    assert rows[-1]["fields"]["margin_cents"] == (None, -100)


def test_same_numbers_under_a_different_label_do_not_match():
    relabelled = HANDBOOK_L8.replace("Sunday ", "Sundae ")
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript(relabelled))
    assert [r["label"] for r in rows if not r["match"]] == ["Sunday"]


def test_swapped_second_monday_and_tuesday_do_not_match():
    lines = HANDBOOK_L8.splitlines()
    lines[8], lines[9] = lines[9], lines[8]  # the last Monday and Tuesday
    rows = compare_transcript(parse_transcript(HANDBOOK_L8), parse_transcript("\n".join(lines)))
    assert sum(not r["match"] for r in rows) == 2


def _assess(text, exit_code=0, level=8, expected=None):
    return assess_level(level, parse_transcript(text) if text is not None else None, exit_code, -7261251,
                        expected if expected is not None else parse_transcript(HANDBOOK_L8))


def test_assess_level_passes_the_handbook_week():
    a = _assess(HANDBOOK_L8)
    assert a["match"] and a["ran"] and a["checks"] == {"exit": True, "practice": True, "level": True, "verdict": True}


@pytest.mark.parametrize("mutate, failed", [
    (lambda t: t, None),
    (lambda t: t.replace("Not ranked: the delivery minimum is 90% of the orders on time.", "Ranked."), "verdict"),
    (lambda t: t.replace("Practice world", "Ranking run"), "practice"),
    (lambda t: t.replace("level 8.", "level 7."), "level"),
])
def test_assess_level_fails_on_each_broken_check(mutate, failed):
    a = _assess(mutate(HANDBOOK_L8))
    assert a["match"] is (failed is None)
    if failed:
        assert a["checks"][failed] is False


def test_assess_level_fails_on_a_nonzero_exit_even_with_a_matching_week():
    a = _assess(HANDBOOK_L8, exit_code=1)
    assert a["match"] is False and a["checks"]["exit"] is False


def test_assess_level_not_run():
    a = _assess(None, exit_code=None)
    assert a["ran"] is False and a["match"] is False


def test_starter_command_only_carries_level_and_seed():
    cmd = starter_command("/x/spread-starter", 7)
    assert cmd == ["/x/spread-starter", "--level", "7", "--seed", "spread-1"]
    with pytest.raises(ValueError):
        starter_command("/x/spread-starter", 9)


def test_counted_run_flag_requires_exit_identity_and_step_count():
    hb = parse_transcript(HANDBOOK_L8)
    assert counted_ok(hb, hb, 0, 1891, 1891) is True
    assert counted_ok(hb, hb, 1, 1891, 1891) is False
    assert counted_ok(hb, hb, 0, 1890, 1891) is False
    empty = parse_transcript("")
    assert counted_ok(empty, empty, 0, 1891, 1891) is False
