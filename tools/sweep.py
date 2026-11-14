"""Paired sweeps: every setting on the same seeds, at most 7 practice worlds at once (a team holds 8).

    python -m tools.sweep --name price1 --seeds dev-1 dev-2 --level 8 \
        --setting "priced price_mult=1.0" --setting "priced price_mult=1.35"

Writes evidence/sweeps/<name>.json: per run the server's end score plus tools.diagnose. Plays practice worlds
only (desk.runner never plays a ranking run). Deletes only worlds this sweep created that have not ended.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from spread.client import Client, SpreadError

from tools.canary import Canary
from tools.diagnose import diagnose
from tools.g0 import team_env

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "sweeps"
MAX_PARALLEL = 6  # + the canary = 7 of the team's 8 practice worlds


def one(setting: str, seed: str, level: int, log_dir: Path) -> dict:
    policy, *params = setting.split()
    cmd = [sys.executable, "-m", "desk.runner", "--level", str(level), "--seed", seed, "--policy", policy]
    for p in params:
        cmd += ["--param", p]
    log = log_dir / f"{setting.replace(' ', '_').replace('=', '')}__{seed}.log"
    started = time.monotonic()
    with open(log, "w", encoding="utf-8") as out:
        code = subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT).returncode
    text = log.read_text(encoding="utf-8")
    world_id: Optional[str] = next((l.split()[2].rstrip(",") for l in text.splitlines() if l.startswith("Practice world ")), None)
    row = {"setting": setting, "seed": seed, "level": level, "worldId": world_id, "exit": code, "seconds": round(time.monotonic() - started, 1)}
    summary_path = ROOT / "runs" / (world_id or "-") / "summary.json"
    if code == 0 and summary_path.exists():
        end = json.loads(summary_path.read_text(encoding="utf-8"))["days"][-1]["score"]
        row.update(score=end, diag=diagnose(world_id))
    else:
        row["error"] = text[-600:]
    print(f"{setting:<32} {seed:<8} exit {code} " + (f"margin {end['marginCents'] / 100:>10,.2f} on time {end['onTimeShare']:.1%} won {end['wonOrders']}"
                                                     if "score" in row else "FAILED"), flush=True)
    return row


def cleanup(world_ids: list) -> list:
    """Deletes this sweep's practice worlds that have not ended (a crashed run holds a slot)."""
    env = team_env()
    client = Client(env.get("SPREAD_URL"), env.get("SPREAD_KEY"))
    deleted = []
    for w in client.worlds():
        if w["worldId"] in world_ids and not w["ended"] and w["kind"] == "practice" and w.get("boardRun") is None:
            try:
                client.world(w["worldId"]).delete()
                deleted.append(w["worldId"])
            except SpreadError as error:
                print(f"could not delete {w['worldId']}: {error}", file=sys.stderr)
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--name", required=True)
    parser.add_argument("--seeds", nargs="+", required=True)
    parser.add_argument("--level", type=int, default=8)
    parser.add_argument("--setting", action="append", required=True, help='"<policy> key=value ..."')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log_dir = OUT / args.name
    log_dir.mkdir(exist_ok=True)
    jobs = [(s, seed) for s in args.setting for seed in args.seeds]
    started = time.monotonic()
    canary = Canary(log_dir / "canary.log").start()
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        rows = list(pool.map(lambda job: one(job[0], job[1], args.level, log_dir), jobs))
    clean = canary.wait()
    deleted = cleanup([r["worldId"] for r in rows if r["worldId"]])
    result = {"name": args.name, "level": args.level, "seeds": args.seeds, "settings": args.setting, "rows": rows,
              "seconds": round(time.monotonic() - started, 1), "deletedUnended": deleted, "canary": clean,
              "serverClean": bool(clean.get("match"))}
    (OUT / f"{args.name}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote evidence/sweeps/{args.name}.json in {result['seconds']} s; deleted unended: {deleted}; canary {'clean' if result['serverClean'] else 'NOT CLEAN: server incident, rerun before trusting'}")


if __name__ == "__main__":
    main()
