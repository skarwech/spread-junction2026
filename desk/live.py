"""The live desk: plays a world whose clock moves by itself (the final, a test final, or a rehearsal).

    python -m desk.live --final --policy priced --param price_mult=1.5 ...      # waits for the (test) final
    python -m desk.live --world <practice id> --level 8 --policy priced ...     # rehearsal; tools.pacer moves the clock

The kit's play_final, made robust:
- the policy is ours (desk.policy), deterministic, rebuilt after any restart from the snapshot and the event log
  (the kit's Desk.rejoin), so the desk can be stopped and started at any time;
- the event stream is supervised: any failure (refused handshake, close 1013, network) reconnects with the last
  seq, and a skipped seq is filled from GET /events;
- every action is validated before it leaves; an invalid one is dropped and logged, so it cannot sink its batch;
- requests go through SafeClient, which never sends a POST twice;
- a final that has already ended (the route keeps returning the last one) is never joined.
Everything the desk sees and sends is logged to runs/<world>/live.jsonl with wall-clock times.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from spread.client import SpreadError, Unreachable, World
from spread.starter import DAY, WEEKDAYS

from desk import actions as A
from desk.client import SafeClient
from desk.journal import write_atomic
from desk.policy import Params, make_desk
from desk.runner import score_line
from tools.g0 import team_env

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


class Log:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(path, "a", encoding="utf-8")

    def __call__(self, kind: str, **fields: Any) -> None:
        self._f.write(json.dumps({"t": round(time.time(), 3), "kind": kind, **fields}, separators=(",", ":")) + "\n")
        self._f.flush()


class QuoteSender:
    """Sends quotes from their own thread and connection, so a quote never waits behind another call. Quotes
    queued while a request is in flight go together (up to 50). A quote whose window has closed is skipped:
    it would be refused and cost a token (rehearsal, 14 Nov: a backlog made 121 quotes arrive too late)."""

    def __init__(self, world: World, log: Log, respond_by: Callable[[str], Optional[int]], now: Callable[[], int]):
        self.world, self.log, self.respond_by, self.now = world, log, respond_by, now
        self._queue: list = []
        self._lock = threading.Condition()
        self._stop = False
        self.sent = self.skipped = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def put(self, quote: dict) -> None:
        with self._lock:
            self._queue.append((time.time(), quote))
            self._lock.notify()

    def close(self, timeout: float = 10.0) -> None:
        with self._lock:
            self._stop = True
            self._lock.notify()
        self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            with self._lock:
                while not self._queue and not self._stop:
                    self._lock.wait()
                if not self._queue:
                    return
                batch, self._queue = self._queue[: A.MAX_BATCH], self._queue[A.MAX_BATCH:]
            for attempt in range(4):  # quotes are safe to resend: a new quote replaces the earlier one
                now = self.now()
                fresh = [(t, q) for t, q in batch if (self.respond_by(q["requestId"]) or 10**12) > now]
                stale = len(batch) - len(fresh)
                self.skipped += stale
                batch = fresh
                if not fresh:
                    self.log("quotes_skipped", n=stale, now=now)
                    break
                try:
                    answers = self.world.act([q for _, q in fresh])
                except Exception as error:  # network or anything else: never let the thread die
                    self.log("quote_error", error=str(error)[:200], n=len(fresh), attempt=attempt)
                    time.sleep(0.3 * (attempt + 1))
                    continue
                self.sent += len(fresh)
                self.log("act", n=len(fresh), types=["quote"] * len(fresh), quotes=[q["requestId"] for _, q in fresh],
                         queued_s=round(time.time() - min(t for t, _ in fresh), 3), skipped=stale,
                         refused=[r.get("reason") for r in answers if not r.get("ok")])
                break


class LiveIO:
    """What the policy's Desk calls `world`: act() validates, sends in batches of 50, logs. With a QuoteSender,
    quotes go through it (the policy does not read quote results) and everything else is sent here at once."""

    def __init__(self, world: World, log: Log, quotes: Optional[QuoteSender] = None):
        self.world, self.log, self.quotes = world, log, quotes
        self.sent = self.dropped = 0

    def act(self, actions: list) -> list:
        results: list = [None] * len(actions)
        valid = []
        for i, action in enumerate(actions):
            found = A.errors(action)
            if found:
                results[i] = {"ok": False, "reason": "not sent: " + "; ".join(found)}
                self.dropped += 1
                self.log("dropped", action=action, errors=found)
            elif self.quotes is not None and action["type"] == "quote":
                self.quotes.put(action)
                results[i] = {"ok": True, "id": "queued"}
            else:
                valid.append(i)
        for k in range(0, len(valid), A.MAX_BATCH):
            idx = valid[k: k + A.MAX_BATCH]
            batch = [actions[i] for i in idx]
            answers = self.world.act(batch)
            self.sent += len(batch)
            for i, r in zip(idx, answers):
                results[i] = r
            self.log("act", n=len(batch), types=[a["type"] for a in batch],
                     quotes=[a["requestId"] for a in batch if a["type"] == "quote"],
                     refused=[r.get("reason") for r in answers if not r.get("ok")])
        return results


def supervised(world: World, after: int, idle: float, log: Log, probe: Optional[Callable[[int], list]] = None,
               silence: float = 10.0) -> Iterator[Optional[dict]]:
    """Events in order without repeats or holes, whatever happens to the connection. Ends when the world is deleted.
    A stream can also go silent without failing (half-open): after `silence` seconds without an event, `probe`
    (GET /events?after=last&limit=1, on a short-timeout client) says whether events exist that the stream did not
    deliver; if so, the stream is reopened (live-desk review, 14 Nov)."""
    last, failures = after, 0
    while True:
        try:
            stream = world.stream(after=last, idle=idle)
            heard, probed, dead = time.time(), 0.0, False
            for event in stream:
                failures = 0
                if event is None:
                    now = time.time()
                    if probe is not None and now - heard > silence and now - probed > silence:
                        probed = now
                        try:
                            dead = bool(probe(last))
                        except Exception as error:
                            log("probe_error", error=str(error)[:200])
                        if dead:
                            log("stream_silent", last=last, silent_s=round(now - heard, 1))
                            break
                    yield None
                    continue
                heard = time.time()
                if event["seq"] <= last:
                    continue
                if event["seq"] != last + 1:  # a hole: fill it from the log first
                    log("gap", after=last, got=event["seq"])
                    for missing in world.events(after=last):
                        if last < missing["seq"] < event["seq"]:
                            last = missing["seq"]
                            yield missing
                last = event["seq"]
                yield event
            if dead:
                stream.close()  # closes the socket; reopen from `last`
                continue
            log("stream_end", last=last)
            return
        except (SpreadError, OSError) as error:  # refused handshake, 1013, network: reconnect from `last`
            failures += 1
            log("stream_error", error=str(error)[:200], failures=failures)
            time.sleep(min(5.0, 0.5 * failures))
            yield None


def play_live(world: World, level: int, policy: str, params: Params, clock: Callable[[], Optional[int]], log: Log,
              quote_world: Optional[World] = None, probe: Optional[Callable[[int], list]] = None) -> dict:
    """Rejoin from the world's own records, then answer events as they come. Returns the last score.
    `quote_world`: the same world on a second client (its own connection), for the quote thread."""
    history = world.events()
    snapshot = world.snapshot()
    ends_at = snapshot["endsAt"]
    if snapshot["now"] >= ends_at:
        log("ended_before_start", now=snapshot["now"])
        return world.score()
    seen = {"now": snapshot["now"]}
    desk_ref: dict = {}
    sender = None
    if quote_world is not None:
        sender = QuoteSender(quote_world, log, lambda rid: (desk_ref["desk"].requests.get(rid) or {}).get("respondBy"), lambda: seen["now"])
    try:
        return _play(world, level, policy, params, clock, log, snapshot, history, seen, desk_ref, sender, probe)
    finally:
        if sender is not None:
            sender.close(timeout=3.0)  # a rejoin starts a fresh thread; the old one must not linger


def _play(world: World, level: int, policy: str, params: Params, clock: Callable[[], Optional[int]], log: Log, snapshot: dict,
          history: list, seen: dict, desk_ref: dict, sender: Optional["QuoteSender"], probe: Optional[Callable[[int], list]] = None) -> dict:
    ends_at = snapshot["endsAt"]
    io = LiveIO(world, log, sender)
    desk = make_desk(policy, io, level, snapshot["now"], params)
    desk_ref["desk"] = desk
    desk.rejoin(snapshot, history)
    desk.send()
    log("rejoined", now=snapshot["now"], events=len(history), orders=len(desk.orders), open_requests=len(snapshot["openRequests"]))
    last = history[-1]["seq"] if history else -1
    for event in supervised(world, last, 1.0, log, probe):
        day = desk.now // DAY
        if event is None:
            tick = clock()  # None when the clock read failed: keep the last known minute, never stall
            if tick is not None:
                desk.now = max(desk.now, tick)
        else:
            desk.now = max(desk.now, event["at"])
        seen["now"] = desk.now
        if event is not None:
            if event["kind"] in ("price_request", "order_won", "order_lost", "deadline_close", "visit_failed", "gig_expired"):
                log("event", seq=event["seq"], at=event["at"], ev=event["kind"],
                    id=(event.get("request") or event.get("order") or {}).get("id") or event.get("requestId") or event.get("orderId"),
                    respondBy=(event.get("request") or {}).get("respondBy"))
            desk.handle(event)
        desk.send()
        if desk.now // DAY > day:
            score = world.score()
            log("day", label=WEEKDAYS[day % 7], score=score)
            print(score_line(WEEKDAYS[day % 7], score), flush=True)
        if desk.now >= ends_at:
            break
    if sender is not None:
        sender.close()
    score = world.score()
    log("end", score=score, sent=io.sent, dropped=io.dropped, quotes_sent=sender.sent if sender else None,
        quotes_skipped=sender.skipped if sender else None)
    return score


def next_final(client: SafeClient, log: Log) -> World:
    """The (test) final that is set and has not ended. GET /v1/final keeps returning the last final after it ends."""
    said = False
    while True:
        try:
            world: Optional[World] = client.world(client.final()["worldId"])
        except SpreadError as error:
            if error.status not in (0, 404):
                raise
            world = None
        if world is not None:
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:
                return world
        if not said:
            print("No final running. Waiting: the organisers set a test final 15 minutes before its start, the final 30 minutes before.", flush=True)
            log("waiting_for_final")
            said = True
        time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--final", action="store_true", help="play the team's copy of the (test) final")
    target.add_argument("--world", metavar="WORLD_ID", help="rehearsal: a practice world whose clock tools.pacer moves")
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--policy", choices=("starter", "priced"), default="priced")
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args()
    params = Params.parse(args.param)
    env = team_env()
    client = SafeClient(env.get("SPREAD_URL"), env.get("SPREAD_KEY"))
    boot = Log(RUNS / "live-boot.jsonl")
    world: Optional[World] = None
    failures = 0
    while True:  # any failure: rebuild from the world's records and go on; the world does not wait for us
        try:
            if world is None:
                world = next_final(client, boot) if args.final else client.world(args.world)
                print(f"{'Final' if args.final else 'Rehearsal'} world {world.id}.", flush=True)
            log = Log(RUNS / world.id / "live.jsonl")
            write_atomic(RUNS / world.id / "live_meta.json", json.dumps({"worldId": world.id, "level": args.level, "policy": args.policy,
                                                                       "params": params.as_dict(), "final": args.final}, indent=1))
            fast = SafeClient(env.get("SPREAD_URL"), env.get("SPREAD_KEY"), timeout=2.0)  # clock and probe: short waits
            fast_world = fast.world(world.id)

            def clock() -> Optional[int]:
                try:
                    return fast.final()["now"] if args.final else fast_world.snapshot()["now"]
                except Exception as error:
                    log("clock_error", error=str(error)[:200])
                    return None

            def probe(after: int) -> list:
                return fast_world.events(after=after, limit=1)

            quote_client = SafeClient(env.get("SPREAD_URL"), env.get("SPREAD_KEY"), timeout=2.0)  # quotes: own connection, short waits
            score = play_live(world, args.level, args.policy, params, clock, log, quote_client.world(world.id), probe)
            break
        except KeyboardInterrupt:
            print("Stopped by hand. The world keeps running; start again with: sh tools/start_final.sh", file=sys.stderr)
            sys.exit(130)
        except Exception as error:  # Unreachable, a 4xx, or a bug on an odd event: never leave the week unattended
            failures += 1
            wait = 3 if isinstance(error, Unreachable) else min(10, 2 * failures)
            print(f"spread: {type(error).__name__}: {str(error)[:300]}. Rejoining in {wait} s (failure {failures}).", file=sys.stderr, flush=True)
            boot("failure", error=f"{type(error).__name__}: {str(error)[:300]}", failures=failures)
            time.sleep(wait)
    print(score_line("End", score), flush=True)
    write_atomic(RUNS / world.id / "live_summary.json", json.dumps({"worldId": world.id, "score": score}, indent=1))


if __name__ == "__main__":
    main()
