"""A test final rehearsal: the pacer runs a practice world on the final's clock, the live desk plays it, and
the desk is killed and restarted mid-week. Then the reveal says which requests were never quoted.

    python -m tools.rehearse --seed dev-2 --speedup 2 --kill-after 240 --policy-param price_mult=1.5 ...

Writes evidence/rehearsal/<world>.json.
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

from desk.client import SafeClient
from tools.g0 import team_env

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "rehearsal"


def downtime(lines: list) -> list:
    """World-minute spans with no desk running: from the last line before a rejoin to the rejoin."""
    spans, last_at = [], None
    for l in lines:
        if l["kind"] == "rejoined" and last_at is not None:
            spans.append([last_at, l["now"]])
        if "at" in l and l["at"] is not None:
            last_at = l["at"]
    return spans


def analyse(world_id: str, kills: list, start: int = 0) -> dict:
    lines = [json.loads(l) for l in (ROOT / "runs" / world_id / "live.jsonl").read_text(encoding="utf-8").splitlines()]
    arrived = {l["id"]: l for l in lines if l["kind"] == "event" and l["ev"] == "price_request" and l["at"] >= start}
    first_quote: dict[str, float] = {}
    for l in lines:
        if l["kind"] == "act":
            for rid in l["quotes"]:
                first_quote.setdefault(rid, l["t"])
    latency = sorted(first_quote[r] - arrived[r]["t"] for r in arrived if r in first_quote and first_quote[r] >= arrived[r]["t"])
    env = team_env()
    client = SafeClient(env.get("SPREAD_URL"), env.get("SPREAD_KEY"))
    world = client.world(world_id)
    reveal = world.reveal()
    outcomes: dict[str, int] = {}
    live_requests = [r for r in reveal["requests"] if r["request"]["arrivedAt"] >= start]
    for r in live_requests:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    late_ids = {x.split()[1] for l in lines if l["kind"] == "act" for x in l["refused"] if x and "is not open" in x}
    q = lambda p: round(latency[min(len(latency) - 1, int(p * len(latency)))], 3) if latency else None
    return {
        "worldId": world_id, "score": world.score(), "kills": kills,
        "start": start, "requests": len(live_requests), "outcomes": outcomes,
        "seenLive": len(arrived), "quotedLive": sum(r in first_quote for r in arrived),
        "quoteLatencySeconds": {"p50": q(.5), "p90": q(.9), "p99": q(.99), "max": latency[-1] if latency else None},
        "streamErrors": sum(l["kind"] == "stream_error" for l in lines), "gaps": sum(l["kind"] == "gap" for l in lines),
        "dropped": sum(l["kind"] == "dropped" for l in lines),
        "lateRefusals": sum(1 for l in lines if l["kind"] == "act" for x in l["refused"] if x and "is not open" in x and x.split()[1] in arrived),
        "quotesSkippedStale": sum(l.get("n", 0) for l in lines if l["kind"] == "quotes_skipped") + sum(l.get("skipped", 0) for l in lines if l["kind"] == "act"),
        "queuedSecondsMax": max((l.get("queued_s", 0) for l in lines if l["kind"] == "act"), default=None),
        "refused": [x for l in lines if l["kind"] == "act" for x in l["refused"]][:20],
        "rejoins": [{k: l[k] for k in ("t", "now", "events", "orders", "open_requests")} for l in lines if l["kind"] == "rejoined"],
        "perRequest": [[r["request"]["arrivedAt"], r["outcome"], r["request"]["id"] in late_ids] for r in live_requests],
        "downtime": downtime(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--seed", default="dev-2")
    parser.add_argument("--speedup", type=float, default=2.0)
    parser.add_argument("--start", type=int, default=4320)
    parser.add_argument("--kill-after", type=float, default=240.0)
    parser.add_argument("--policy-param", action="append", default=[])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pacer_log = open(OUT / "pacer.log", "w", encoding="utf-8")
    pacer = subprocess.Popen([sys.executable, "-u", "-m", "tools.pacer", "--level", "8", "--seed", args.seed, "--speedup", str(args.speedup),
                              "--start", str(args.start)], cwd=ROOT, stdout=subprocess.PIPE, stderr=pacer_log, text=True)
    world_id = pacer.stdout.readline().split()[-1]
    pacer.stdout.readline()  # "PACER start": the world is at the start minute; the desk joins now
    desk_cmd = [sys.executable, "-u", "-m", "desk.live", "--world", world_id, "--level", "8", "--policy", "priced"]
    for p in args.policy_param:
        desk_cmd += ["--param", p]
    desk_log = open(OUT / f"{world_id}.desk.log", "w", encoding="utf-8")
    desk = subprocess.Popen(desk_cmd, cwd=ROOT, stdout=desk_log, stderr=subprocess.STDOUT)
    kills = []
    if args.kill_after > 0:
        try:
            desk.wait(timeout=args.kill_after)
        except subprocess.TimeoutExpired:
            desk.send_signal(signal.SIGKILL)
            desk.wait()
            kills.append({"wallAfterStart": args.kill_after, "downSeconds": 5})
            time.sleep(5)
            desk = subprocess.Popen(desk_cmd, cwd=ROOT, stdout=desk_log, stderr=subprocess.STDOUT)
    for line in pacer.stdout:
        pacer_log.write(line)
    pacer.wait()
    desk.wait(timeout=120)
    result = analyse(world_id, kills, args.start)
    (OUT / f"{world_id}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("worldId", "requests", "outcomes", "lateRefusals", "quotesSkippedStale", "queuedSecondsMax", "quoteLatencySeconds", "streamErrors", "gaps", "dropped", "rejoins")}, indent=1))
    print("score", json.dumps(result["score"]))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--analyse":  # --analyse <world> <start>
        print(json.dumps(analyse(sys.argv[2], [], int(sys.argv[3])), indent=1))
    else:
        main()
