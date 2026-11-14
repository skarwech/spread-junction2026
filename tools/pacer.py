"""Moves a practice world's clock in real time, at the final's speeds, so the live desk can rehearse.

    python -m tools.pacer --level 8 --seed dev-2 --speedup 3       # creates the world, prints its id, then paces it

Final speeds (API.md:120): 18 s per hour on weekdays 06:00-22:00, 6 s on Saturday, 9 s on the last Monday,
3 s at night, on Sunday and after the last Monday 22:00. `--speedup 3` runs three times as fast (quote
windows of 1.5 s instead of 4.5 s: a harder test). The pacer only calls advance; the desk never does.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from desk.client import SafeClient
from tools.g0 import team_env

ROOT = Path(__file__).resolve().parents[1]
HOUR, DAY = 60, 1440


def seconds_per_hour(minute: int) -> float:
    day, hour = minute // DAY, (minute % DAY) // HOUR
    if day >= 8 and not (day == 7 and hour < 22):  # after the last Monday 22:00
        return 3.0
    if not 6 <= hour < 22:
        return 3.0
    return {5: 6.0, 6: 3.0, 7: 9.0}.get(day, 18.0)  # Sat, Sun, last Monday; weekdays 18


def main() -> None:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--level", type=int, default=8)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--speedup", type=float, default=1.0)
    parser.add_argument("--start", type=int, default=0, help="first world minute (a test final starts Thursday 00:00 = 4320)")
    args = parser.parse_args()
    env = team_env()
    client = SafeClient(env.get("SPREAD_URL"), env.get("SPREAD_KEY"))
    world = client.create(level=args.level, seed=args.seed, board=False)
    folder = ROOT / "runs" / world.id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pacer.json").write_text(json.dumps(vars(args) | {"worldId": world.id}), encoding="utf-8")
    print(f"PACER world {world.id}", flush=True)
    snap = world.snapshot()
    now, ends = snap["now"], snap["endsAt"]
    if args.start > now:
        world.advance(to=args.start)
        now = args.start
    print(f"PACER start {now}", flush=True)
    time.sleep(2.0)  # let the desk connect first
    wall, target = time.monotonic(), float(now)
    while now < ends:
        time.sleep(0.2)
        t = time.monotonic()
        target += (t - wall) * args.speedup * HOUR / seconds_per_hour(int(target))
        wall = t
        to = min(ends, int(target))
        if to > now:
            now = world.advance(to=to)["now"]
    print(f"PACER end {now}", flush=True)


if __name__ == "__main__":
    main()
