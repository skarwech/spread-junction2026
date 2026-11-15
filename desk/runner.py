"""Plays a practice world through the desk's core: every call journaled, the books folded from the events,
and a restart that picks up exactly where a killed desk stopped.

    python -m desk.runner --level 8 --seed spread-1      # a new practice world
    python -m desk.runner --resume <worldId>             # after a kill: replay the journal, then go on live

The policy for now is the kit's starter (spread.starter.Desk), unchanged: the week must equal the handbook's.
Never plays a ranking run or the final.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from spread.client import Unreachable
from spread.starter import DAY, WAKE_ON, WEEKDAYS

from desk.client import SafeClient as Client
from desk.journal import Journal, write_atomic
from desk.policy import Params, make_desk
from desk.state import State
from desk.worldio import WorldIO
from tools.g0 import team_env

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def score_line(label: str, score: dict) -> str:
    """The starter's printed line (spread.starter.report), so tools.g0 can compare it with the handbook."""
    orders = f"{score['wonOrders']:>4} orders  {score['onTimeShare']:6.1%} on time  {score['undeliveredShare']:5.1%} not delivered"
    return f"{label:<9}  margin €{score['marginCents'] / 100:>11,.2f}  revenue €{score['revenueCents'] / 100:>11,.2f}  {orders}"


def play(io: WorldIO, level: int, state: State, policy: str = "starter", params: Params = Params()) -> list[dict]:
    """The kit's play_practice, step for step, plus the books at each midnight next to the server's score."""
    snapshot = io.snapshot()
    desk, ends_at = make_desk(policy, io, level, snapshot["now"], params), snapshot["endsAt"]
    days = []
    while desk.now < ends_at:
        day, midnight = desk.now // DAY, (desk.now // DAY + 1) * DAY
        actions, desk.outbox = desk.outbox, []
        step = io.advance(until=WAKE_ON, max=min(ends_at, midnight), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            desk.handle(event)
        if desk.now // DAY > day:
            days.append({"label": WEEKDAYS[day % 7], "score": io.score(), "ours": state.summary()})
            if not io.replaying:
                print(score_line(days[-1]["label"], days[-1]["score"]), flush=True)
    days.append({"label": "End", "score": io.score(), "ours": state.summary()})
    return days


def run(world_id: str, client: Client, level: int, resumed: bool) -> dict:
    folder = RUNS / world_id
    state = State()
    journal = Journal(folder / "journal.jsonl")
    io = WorldIO(client.world(world_id), journal, on_results=state.apply_results, on_events=state.apply_events)
    io.on_clock = state.set_clock
    started = time.monotonic()
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    try:
        days = play(io, level, state, meta.get("policy", "starter"), Params(**meta.get("params", {})))
    except BaseException:
        journal.close()
        raise
    summary = {
        **meta,
        "days": days,
        "transcript": [f"{'Ranking run' if meta.get('board') else 'Practice world'} {world_id}, level {level}."] + [score_line(d["label"], d["score"]) for d in days],
        "stats": io.stats,
        "journalCalls": len(journal.calls),
        "fingerprint": state.fingerprint(),
        "trustTop": sorted(state.trust().items(), key=lambda kv: -kv[1])[:10],
        "lastRunSeconds": round(time.monotonic() - started, 1),
        "resumedLastRun": resumed,
    }
    write_atomic(folder / "summary.json", json.dumps(summary, indent=1))
    write_atomic(folder / "transcript.txt", "\n".join(summary["transcript"]) + "\n")
    journal.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--seed")
    parser.add_argument("--resume", metavar="WORLD_ID")
    parser.add_argument("--policy", choices=("starter", "priced"), default="starter")
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="policy parameter, e.g. price_mult=1.35")
    args = parser.parse_args()
    params = Params.parse(args.param)
    env = team_env()
    client = Client(env.get("SPREAD_URL"), env.get("SPREAD_KEY"))
    if args.resume:
        world_id = args.resume
        meta_path = RUNS / world_id / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["resumes"] = meta.get("resumes", 0) + 1
        write_atomic(meta_path, json.dumps(meta, indent=1))
        level = meta["level"]
    else:
        world = client.create(level=args.level, seed=args.seed, board=False)
        world_id, level = world.id, args.level
        (RUNS / world_id).mkdir(parents=True, exist_ok=True)
        meta = {"worldId": world_id, "level": level, "seed": args.seed, "policy": args.policy, "params": params.as_dict(), "resumes": 0}
        write_atomic(RUNS / world_id / "meta.json", json.dumps(meta, indent=1))
        print(f"Practice world {world_id}, level {level}. Resume after a stop with: python -m desk.runner --resume {world_id}", flush=True)
    resumed = bool(args.resume)
    for attempt in range(1, 61):  # a server restart lasts up to a minute (API.md:157)
        try:
            summary = run(world_id, client, level, resumed=resumed)
            break
        except Unreachable as error:  # rebuild from the journal and go on, as after a kill
            print(f"spread: {error}. Resuming from the journal in 5 s (attempt {attempt}).", file=sys.stderr, flush=True)
            time.sleep(5)
            resumed = True
    else:
        sys.exit(f"gave up: the server did not answer for 60 attempts. Resume later with --resume {world_id}")
    print(score_line("End", summary["days"][-1]["score"]), flush=True)
    print(f"stats {json.dumps(summary['stats'])} fingerprint {summary['fingerprint']}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
