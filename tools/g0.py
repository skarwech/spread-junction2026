"""Gate G0: run the unmodified kit starter on seed spread-1 and check it against the handbook to the cent.

    python -m tools.g0 run       # plays L8, L7, L6 with the CLI, plus one L8 run that counts requests
    python -m tools.g0 report    # compares the saved transcripts and writes evidence/g0/result.json

Never plays a ranking run or the final: commands are built by `starter_command`, which can only emit
--level and --seed, and every transcript must start with "Practice world".
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple, Optional

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "g0"
EXPECTED = ROOT / "expected" / "starter_spread-1.json"
SEED = "spread-1"
LEVELS = (8, 7, 6)
FIELDS = ("margin_cents", "revenue_cents", "orders", "on_time_permille", "undelivered_permille")
UTF8 = "utf-8"

# One score line of the starter, in its exact print format (starter.report): a drift in the format
# makes the line unparsed, so it counts as missing (a mismatch) rather than being read loosely.
MONEY = r"-?\d{1,3}(?:,\d{3})*\.\d{2}"
SHARE = r"\d{1,3}\.\d"
SCORE_LINE = re.compile(
    rf"^(?P<label>\w+)\s+margin €\s*(?P<margin>{MONEY})\s+revenue €\s*(?P<revenue>{MONEY})"
    rf"\s+(?P<orders>\d+) orders\s+(?P<on_time>{SHARE})% on time\s+(?P<undelivered>{SHARE})% not delivered\s*$"
)
WORLD_LINE = re.compile(r"^(?P<kind>Practice world|Ranking run|Final world) (?P<id>w[0-9a-f]+)(?:, level (?P<level>\d))?")


class DayLine(NamedTuple):
    label: str
    margin_cents: int
    revenue_cents: int
    orders: int
    on_time_permille: int  # the printed share to one decimal, as tenths of a percent
    undelivered_permille: int


class Transcript(NamedTuple):
    world_id: Optional[str]
    days: tuple[DayLine, ...]
    verdict: Optional[str]
    kind: Optional[str] = None
    level: Optional[int] = None


def money_cents(text: str) -> int:
    """'-72,612.51' -> -7261251, with integer arithmetic only."""
    text = text.strip().replace(",", "")
    sign = -1 if text.startswith("-") else 1
    whole, cents = text.lstrip("-").split(".")
    return sign * (int(whole) * 100 + int(cents))


def tenths(text: str) -> int:
    whole, frac = text.split(".")
    return int(whole) * 10 + int(frac)


def parse_transcript(text: str) -> Transcript:
    world_id = verdict = kind = level = None
    days = []
    for line in text.splitlines():
        world = WORLD_LINE.match(line)
        score = SCORE_LINE.match(line)
        if world:
            world_id, kind = world["id"], world["kind"]
            level = int(world["level"]) if world["level"] else None
        elif score:
            days.append(DayLine(score["label"], money_cents(score["margin"]), money_cents(score["revenue"]),
                                int(score["orders"]), tenths(score["on_time"]), tenths(score["undelivered"])))
        elif line.startswith(("Ranked.", "Not ranked")):
            verdict = line.strip()
    return Transcript(world_id, tuple(days), verdict, kind, level)


def compare_transcript(expected: Transcript, actual: Transcript) -> list[dict]:
    """One row per line, in order. A missing, extra or relabelled line is a mismatch."""
    rows = []
    for i, want in enumerate(expected.days):
        got = actual.days[i] if i < len(actual.days) else None
        fields = {f: (getattr(want, f), getattr(got, f) if got else None) for f in FIELDS}
        match = got is not None and got.label == want.label and all(a == b for a, b in fields.values())
        rows.append({"label": want.label, "actual_label": got.label if got else None, "expected": want._asdict(),
                     "actual": got._asdict() if got else None, "fields": fields, "match": match})
    for extra in actual.days[len(expected.days):]:
        rows.append({"label": extra.label, "actual_label": extra.label, "expected": None, "actual": extra._asdict(),
                     "fields": {f: (None, getattr(extra, f)) for f in FIELDS}, "match": False})
    return rows


def compare_end(expected_margin: int, actual: Optional[Transcript]) -> dict:
    end = next((d for d in reversed(actual.days) if d.label == "End"), None) if actual else None
    got = end.margin_cents if end else None
    return {"expected": expected_margin, "actual": got, "match": got == expected_margin}


def assess_level(level: int, actual: Optional[Transcript], exit_code: Optional[int], expected_end: int,
                 expected_week: Optional[Transcript] = None) -> dict:
    """Whether one level's run reproduces the handbook: a clean exit, a practice world at the asked level,
    the same end margin and, where the handbook prints the whole week, every line and the verdict."""
    ran = actual is not None and bool(actual.days)
    rows = compare_transcript(expected_week, actual) if (expected_week and actual) else []
    checks = {
        "exit": exit_code == 0,
        "practice": bool(actual) and actual.kind == "Practice world",
        "level": bool(actual) and actual.level == level,
        "verdict": expected_week is None or (bool(actual) and actual.verdict == expected_week.verdict),
    }
    end = compare_end(expected_end, actual)
    match = ran and end["match"] and all(checks.values()) and all(r["match"] for r in rows)
    return {"ran": ran, "rows": rows, "end": end, "checks": checks, "match": match,
            "world_id": actual.world_id if actual else None, "verdict": actual.verdict if actual else None}


def counted_ok(counted: Transcript, cli: Transcript, exit_code: Optional[int], advance_steps: Optional[int], expected_steps: int) -> bool:
    """The instrumented run is trustworthy only if it exited cleanly, played the identical week and took the documented steps."""
    return (exit_code == 0 and bool(counted.days) and counted.days == cli.days and counted.verdict == cli.verdict
            and advance_steps == expected_steps)


def load_env(path: Path) -> dict[str, str]:
    """KEY=value pairs from a .env file. Values are never printed."""
    if not path.exists():
        return {}
    pairs = {}
    for raw in path.read_text(encoding=UTF8).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        pairs[key] = value.strip("'\"")
    return pairs


def team_env() -> dict[str, str]:
    """The process environment, with non-empty .env values taking precedence."""
    file_values = {k: v for k, v in load_env(ROOT / ".env").items() if v}
    return {**os.environ, **file_values}


def starter_command(executable: str, level: int) -> list[str]:
    """The only command G0 runs: a practice world at a level on the G0 seed. Nothing else can be added."""
    if level not in range(1, 9):
        raise ValueError(f"level {level} is not 1-8")
    return [executable, "--level", str(level), "--seed", SEED]


def _wait_all(procs: dict[str, subprocess.Popen], started: dict[str, float]) -> dict[str, dict]:
    """Waits for every process, recording each one's own exit time."""
    meta: dict[str, dict] = {}
    while len(meta) < len(procs):
        for name, proc in procs.items():
            if name not in meta and proc.poll() is not None:
                meta[name] = {"exit": proc.returncode, "elapsed_s": round(time.monotonic() - started[name], 1)}
                print(f"finished {name}: exit {proc.returncode} in {meta[name]['elapsed_s']} s", flush=True)
        time.sleep(0.2)
    return meta


def run(levels: tuple[int, ...] = LEVELS, counted: bool = True) -> int:
    env = team_env()
    if not env.get("SPREAD_KEY"):
        print("SPREAD_KEY is empty. Add your team key to .env (SPREAD_KEY=...) and run again.", file=sys.stderr)
        return 2
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    jobs = {f"starter_L{lv}": starter_command(str(ROOT / ".venv" / "bin" / "spread-starter"), lv) for lv in levels}
    if counted:
        jobs["counted_L8"] = [sys.executable, "-m", "tools.count_requests", *starter_command("", 8)[1:]]
    started: dict[str, float] = {}
    procs: dict[str, subprocess.Popen] = {}
    with contextlib.ExitStack() as files:
        try:
            for name, cmd in jobs.items():
                out = files.enter_context(open(EVIDENCE / f"{name}_{SEED}.txt", "w", encoding=UTF8))
                started[name] = time.monotonic()
                procs[name] = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
                print(f"started {name}: {' '.join(cmd[-4:])}", flush=True)
            meta = _wait_all(procs, started)
        finally:  # a starter stopped by SIGTERM deletes its practice world
            for proc in procs.values():
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=30)
    (EVIDENCE / "runs.json").write_text(json.dumps(meta, indent=1), encoding=UTF8)
    return 0 if all(m["exit"] == 0 for m in meta.values()) else 1


def read_transcript(name: str) -> Optional[Transcript]:
    path = EVIDENCE / f"{name}_{SEED}.txt"
    return parse_transcript(path.read_text(encoding=UTF8)) if path.exists() else None


def report() -> dict:
    spec = json.loads(EXPECTED.read_text(encoding=UTF8))
    expected_l8 = parse_transcript((ROOT / spec["L8"]["transcript"]).read_text(encoding=UTF8))
    meta_path = EVIDENCE / "runs.json"
    meta = json.loads(meta_path.read_text(encoding=UTF8)) if meta_path.exists() else {}
    ends = {"8": expected_l8.days[-1].margin_cents, "7": spec["L7"]["end_margin_cents"], "6": spec["L6"]["end_margin_cents"]}
    levels = {}
    for lv, end in ends.items():
        run_meta = meta.get(f"starter_L{lv}", {})
        assessed = assess_level(int(lv), read_transcript(f"starter_L{lv}"), run_meta.get("exit"), end, expected_l8 if lv == "8" else None)
        levels[lv] = {**assessed, **run_meta}
    counted = read_transcript("counted_L8") or Transcript(None, (), None)
    counted_text = (EVIDENCE / f"counted_L8_{SEED}.txt").read_text(encoding=UTF8) if counted.days else ""
    requests = re.search(r"^REQUESTS (\d+) (\{.*\})$", counted_text, re.M)
    by_route = json.loads(requests[2]) if requests else {}
    counted_meta = meta.get("counted_L8", {})
    # API.md's "takes 1,891" counts the steps: one advance per stop of the clock.
    advance = by_route.get("POST /v1/worlds/{id}/advance")
    l8 = read_transcript("starter_L8") or Transcript(None, (), None)
    result = {
        "seed": SEED,
        "levels": levels,
        "counted": {
            "ran": bool(counted.days),
            "requests": int(requests[1]) if requests else None,
            "advance_requests": advance,
            "by_route": by_route,
            "expected_requests": spec["L8"]["requests"],
            "same_as_cli": bool(counted.days) and counted.days == l8.days and counted.verdict == l8.verdict,
            "ok": counted_ok(counted, l8, counted_meta.get("exit"), advance, spec["L8"]["requests"]),
            **counted_meta,
        },
    }
    result["g0_pass"] = all(levels[lv]["match"] for lv in ends)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "result.json").write_text(json.dumps(result, indent=1), encoding=UTF8)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("command", choices=("run", "report"))
    args = parser.parse_args()
    if args.command == "run":
        sys.exit(run())
    result = report()
    for lv in ("8", "7", "6"):
        e = result["levels"][lv]
        state = "MATCH" if e["match"] else "NOT RUN" if not e["ran"] else "MISMATCH"
        print(f"L{lv}: {state}  end {e['end']}  checks {e['checks']}")
    c = result["counted"]
    print(f"L8 advance steps: {c['advance_requests']} vs {c['expected_requests']} in API.md; all requests: {c['requests']}; counted run ok: {c['ok']}")
    print("G0 PASS" if result["g0_pass"] else "G0 not passed")


if __name__ == "__main__":
    main()
