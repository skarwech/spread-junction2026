"""Run the selected policy through each current ranked week, level by level.

    .venv/bin/python -m tools.rank_all --dry-run
    .venv/bin/python -m tools.rank_all

This intentionally creates ranking runs (not disposable practice worlds). It checks the current round and
the team's progress before every world, runs one world at a time, and saves evidence after each completed week.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

from spread.client import Unreachable

from desk.client import SafeClient
from desk.journal import write_atomic
from desk.policy import Params
from desk.runner import run as run_world, score_line
from tools.g0 import team_env

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "ranking_current"
DEFAULT_PARAMS = [
    "price_mult=1.5", "fee_mode=deadline", "fee_open=0.9", "fee_cap=1.85", "fee_lead_h=2",
    "trust_markup=0.01", "target_win=0.4", "cost_floor=1.15", "intake_cap=80", "m_min=1.0",
    "options=safe", "max_drive_h=6", "min_slack_h=7", "night_hold=1",
]
L1_PARAMS = [
    # L1 ignores quote prices and allows one fee step. This profile was selected on four fresh holdout weeks.
    "fee_open=0.85", "fee_steps=1", "max_drive_h=4", "min_slack_h=7", "open_order_cap=0",
]


def params_for_level(level: int, overrides: list[str] | None = None) -> Params:
    """Use the validated L1 fee/risk profile while retaining the L8 profile at other levels."""
    profile = DEFAULT_PARAMS + (L1_PARAMS if level == 1 else [])
    return Params.parse(profile + (overrides or []))


def save(path: Path, data: dict) -> None:
    write_atomic(path, json.dumps(data, indent=2) + "\n")


def current_board(client: SafeClient, level: int) -> dict:
    board = client.board(level)
    current = board.get("current")
    if not current:
        raise RuntimeError(f"L{level}: no current ranking round")
    return current


def team_entry(board: dict, team_id: str) -> dict:
    return next((t for t in board.get("teams", []) if t.get("team") == team_id), {})


def run_one(client: SafeClient, level: int, week: int, season: int, policy: str, params: Params) -> dict:
    current = current_board(client, level)
    team = team_entry(current, TEAM_ID)
    if current.get("season") != season:
        raise RuntimeError(f"L{level}: round changed from season {season} to {current.get('season')}; stopping before creating a mixed-round run")
    if team.get("played") != week - 1:
        raise RuntimeError(f"L{level}: expected {week - 1} completed runs, board reports {team.get('played')}")

    world = client.create(level=level, board=True)
    world_id = world.id
    folder = ROOT / "runs" / world_id
    folder.mkdir(parents=True, exist_ok=True)
    meta = {
        "worldId": world_id, "level": level, "seed": None, "policy": policy,
        "params": params.as_dict(), "resumes": 0, "board": True,
        "season": season, "boardRun": week,
    }
    write_atomic(folder / "meta.json", json.dumps(meta, indent=1))

    # A post-create read validates the server assigned the expected ranked slot. If it fails, still serve the
    # run we just created: deleting or abandoning a ranking run does not undo its score.
    try:
        record = next((w for w in client.worlds() if w.get("worldId") == world_id), {})
        if record and (record.get("season") != season or record.get("boardRun") != week):
            print(f"warning: {world_id} metadata reports season={record.get('season')} boardRun={record.get('boardRun')}; serving it anyway", flush=True)
    except Exception as error:
        print(f"warning: could not verify {world_id} metadata ({error}); serving it anyway", flush=True)

    log_path = EVIDENCE / f"L{level}_week{week}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"L{level} week {week}/5: started ranking run {world_id}", flush=True)
    with log_path.open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        summary = None
        for attempt in range(1, 61):
            try:
                summary = run_world(world_id, client, level, resumed=attempt > 1)
                break
            except Unreachable as error:
                print(f"spread: {error}. Resuming from the journal in 5 s (attempt {attempt}).", file=sys.stderr, flush=True)
                time.sleep(5)
        if summary is None:
            raise RuntimeError(f"{world_id}: server unreachable after 60 attempts; see {log_path}")

    score = summary["days"][-1]["score"]
    row = {
        "level": level, "week": week, "season": season, "worldId": world_id,
        "score": score, "seconds": summary["lastRunSeconds"], "log": str(log_path.relative_to(ROOT)),
    }
    print(f"L{level} week {week}/5: {score_line('End', score)}", flush=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", nargs="+", type=int, default=[8, 7, 6, 5, 4, 3, 2, 1])
    parser.add_argument("--weeks", type=int, default=5)
    parser.add_argument("--policy", choices=("priced", "starter"), default="priced")
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--dry-run", action="store_true", help="check boards and progress without creating worlds")
    args = parser.parse_args()
    if not 1 <= args.weeks <= 5 or not args.levels or any(not 1 <= n <= 8 for n in args.levels) or len(set(args.levels)) != len(args.levels):
        parser.error("levels must be unique integers 1–8 and weeks must be 1–5")
    params_by_level = {level: params_for_level(level, args.param) for level in args.levels}
    env = team_env()
    client = SafeClient(env.get("SPREAD_URL"), env.get("SPREAD_KEY"))

    global TEAM_ID
    final_board = json.loads((ROOT / "evidence" / "final_leaderboard.json").read_text(encoding="utf-8"))
    TEAM_ID = final_board["team"]["team"]
    active = [w for w in client.worlds() if not w.get("ended")]
    if active:
        ids = ", ".join(f"{w.get('worldId')} ({w.get('kind')} L{w.get('level')})" for w in active)
        raise RuntimeError(f"active worlds exist; finish or resume them before starting rankings: {ids}")

    boards = {level: current_board(client, level) for level in args.levels}
    seasons = {b.get("season") for b in boards.values()}
    if len(seasons) != 1 or None in seasons:
        raise RuntimeError(f"requested levels are not in one active season: {sorted(str(x) for x in seasons)}")
    season = next(iter(seasons))
    plan = []
    for level in args.levels:
        team = team_entry(boards[level], TEAM_ID)
        if not team:
            raise RuntimeError(f"L{level}: team {TEAM_ID!r} is missing from the board")
        played = team.get("played", 0)
        if played >= args.weeks:
            print(f"L{level}: already has {played}/{args.weeks} requested runs; skipping")
            continue
        plan.extend((level, week) for week in range(played + 1, args.weeks + 1))
    print(f"Season {season}: {len(plan)} ranked runs planned across levels {args.levels}; policy={args.policy}; "
          f"paramsByLevel={{{', '.join(f'{level}: {params.as_dict()}' for level, params in params_by_level.items())}}}", flush=True)
    if args.dry_run:
        return

    output = EVIDENCE / f"season{season}.json"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    data = {
        "status": "running", "season": season, "board": next(iter(boards.values())).get("name"),
        "team": TEAM_ID, "policy": args.policy,
        "paramsByLevel": {str(level): params.as_dict() for level, params in params_by_level.items()},
        "levels": args.levels, "weeksRequested": args.weeks, "runs": [],
    }
    save(output, data)
    for level, week in plan:
        row = run_one(client, level, week, season, args.policy, params_by_level[level])
        data["runs"].append(row)
        save(output, data)

    totals = {}
    for level in args.levels:
        runs = [r for r in data["runs"] if r["level"] == level]
        if runs:
            board = current_board(client, level)
            result = team_entry(board, TEAM_ID)
            totals[str(level)] = {
                "played": result.get("played"), "ranked": result.get("ranked"), "rank": result.get("rank"),
                "marginCents": result.get("marginCents"), "onTimeShare": result.get("onTimeShare"),
                "weeks": runs,
            }
    data["status"] = "completed"
    data["levelsResult"] = totals
    save(output, data)
    print(f"Completed {len(data['runs'])} ranking runs; evidence: {output.relative_to(ROOT)}", flush=True)


TEAM_ID = ""


if __name__ == "__main__":
    main()
