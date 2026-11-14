"""Experiment E11, restart invariance: kill the desk with SIGKILL at random moments, resume it, and check that
the week ends exactly as an uninterrupted run (margin to the cent, same books fingerprint).

    python -m tools.restart_test --runs 6 --kills 3 --level 8 --seed spread-1

Writes evidence/restart/result.json. Plays practice worlds only (desk.runner never plays a ranking run).
"""
from __future__ import annotations

import argparse
import json
import random
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "restart"


def world_id_of(log: Path) -> str | None:
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    for line in text.splitlines():
        if line.startswith("Practice world "):
            return line.split()[2].rstrip(",")
    return None


def journal_tail(world_id: str) -> dict:
    """Where the desk was when it was killed: calls journaled, the last one, and whether it was in flight."""
    from desk.journal import load
    calls = load(ROOT / "runs" / world_id / "journal.jsonl")
    last = calls[-1] if calls else None
    minute = next((c.resp["now"] for c in reversed(calls) if c.resp and c.op == "advance"), 0)
    return {"calls": len(calls), "lastOp": last.op if last else None, "inFlight": bool(last and last.resp is None), "minute": minute}


def one_run(index: int, args: argparse.Namespace, rng: random.Random, report: dict) -> None:
    log = OUT / f"run{index}.log"
    cmd = [sys.executable, "-m", "desk.runner", "--level", str(args.level), "--seed", args.seed]
    kills = []
    with open(log, "w", encoding="utf-8") as out:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
        for k in range(args.kills if index > 0 else 0):  # run 0 is the uninterrupted control
            delay = rng.uniform(args.min_delay, args.max_delay)
            try:
                proc.wait(timeout=delay)
                break  # finished before the kill
            except subprocess.TimeoutExpired:
                pass
            proc.send_signal(signal.SIGKILL)
            proc.wait()
            wid = world_id_of(log)
            if wid is None:
                kills.append({"after_s": round(delay, 1), "note": "killed before the world existed"})
                proc = subprocess.Popen(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
                continue
            kills.append({"after_s": round(delay, 1), **journal_tail(wid)})
            out.write(f"--- SIGKILL {k + 1}, resuming\n")
            out.flush()
            proc = subprocess.Popen([sys.executable, "-m", "desk.runner", "--resume", wid], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
        code = proc.wait()
    wid = world_id_of(log)
    summary_path = ROOT / "runs" / (wid or "-") / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    end = summary.get("days", [{}])[-1].get("score", {}) if summary else {}
    report[index] = {"run": index, "worldId": wid, "exit": code, "kills": kills, "endMarginCents": end.get("marginCents"),
                     "fingerprint": summary.get("fingerprint"), "lastStats": summary.get("stats"), "resumes": summary.get("resumes")}


def main() -> None:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--runs", type=int, default=6, help="killed runs, plus one uninterrupted control")
    parser.add_argument("--kills", type=int, default=3)
    parser.add_argument("--level", type=int, default=8)
    parser.add_argument("--seed", default="spread-1")
    parser.add_argument("--min-delay", type=float, default=4.0)
    parser.add_argument("--max-delay", type=float, default=18.0)
    parser.add_argument("--rng", type=int, default=11)
    args = parser.parse_args()
    if args.runs + 2 > 8:
        sys.exit("at most 6 killed runs + 1 control + 1 canary: a team holds 8 practice worlds")
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.rng)
    report: dict = {}
    threads = [threading.Thread(target=one_run, args=(i, args, random.Random(rng.random()), report)) for i in range(args.runs + 1)]
    started = time.monotonic()
    from tools.canary import Canary
    canary = Canary(OUT / "canary.log").start()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    clean = canary.wait()
    runs = [report[i] for i in sorted(report)]
    control = runs[0]
    for r in runs:
        r["sameMargin"] = r["endMarginCents"] is not None and r["endMarginCents"] == control["endMarginCents"]
        r["sameBooks"] = r["fingerprint"] is not None and r["fingerprint"] == control["fingerprint"]
    result = {"level": args.level, "seed": args.seed, "seconds": round(time.monotonic() - started, 1), "runs": runs,
              "kills": sum(len(r["kills"]) for r in runs), "inFlightKills": sum(k.get("inFlight", False) for r in runs for k in r["kills"]),
              "allSame": all(r["sameMargin"] and r["sameBooks"] and r["exit"] == 0 for r in runs), "canary": clean,
              "serverClean": bool(clean.get("match"))}
    (OUT / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    for r in runs:
        print(f"run {r['run']}: kills {len(r['kills'])} end {r['endMarginCents']} fp {r['fingerprint']} same {r['sameMargin'] and r['sameBooks']} exit {r['exit']}")
    print(f"kills {result['kills']} (in flight {result['inFlightKills']}); all identical: {result['allSame']}; canary {'clean' if result['serverClean'] else 'NOT CLEAN'}")


if __name__ == "__main__":
    main()
