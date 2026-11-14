"""WorldIO: the desk's only door to a world. It records every call in the journal and, after a restart,
replays the journal instead of calling the world, then goes live where the journal ends.

Replay is also a determinism check: each call the desk makes again must equal the recorded one, or
`ReplayDivergence` stops the desk (a decision that is not a pure function of what the world said).

The one call that may have been in flight when the desk was killed is recovered from the world itself:
- reads (snapshot, score, events) are simply made again;
- `act` and `advance` are checked against the snapshot: a post the world accepted shows as a new gig at the
  call's minute with the same stops; a clock that moved or new events show that an advance happened.
  If the call happened, its answer is rebuilt from the snapshot and `GET /events`; if not, it is sent again.
  Quotes, reprices and withdraws carry no new id, and sending them again is harmless.
Each `act` and `advance` carries at most 50 actions in one HTTP request, so it applied wholly or not at all.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from desk import actions as A
from desk.journal import Journal, normal

ResultsListener = Callable[[list, list], None]
EventsListener = Callable[[list], None]


class ReplayDivergence(RuntimeError):
    pass


def stops_key(stops: Sequence[dict]) -> tuple:
    return tuple((s["orderId"], s["leg"], s["kind"]) for s in stops)


class WorldIO:
    def __init__(self, live: Any, journal: Journal, on_results: Optional[ResultsListener] = None,
                 on_events: Optional[EventsListener] = None, validate: bool = True):
        self.live, self.journal = live, journal  # live: a spread.client.World
        self.on_results = on_results or (lambda actions, results: None)
        self.on_events = on_events or (lambda events: None)
        self.on_clock: Callable[[int], None] = lambda now: None
        self.validate = validate
        self.pos = 0  # the next journal call to replay
        self.now: Optional[int] = None
        self.last_seq = -1
        self.known_gigs: set[str] = set()
        self.stats = {"replayed": 0, "live": 0, "recovered_applied": 0, "recovered_resent": 0, "recovered_read": 0, "gaps_filled": 0}

    @property
    def replaying(self) -> bool:
        return self.pos < len(self.journal.calls)

    # ---- the calls ---------------------------------------------------------------------------------

    def snapshot(self) -> dict:
        snap = self._call("snapshot", {}, lambda req: self.live.snapshot(), self._recover_read)
        self.now = snap["now"]
        return snap

    def score(self) -> dict:
        return self._call("score", {}, lambda req: self.live.score(), self._recover_read)

    def act(self, actions: Sequence[dict]) -> list:
        """Mid-step actions, applied at the current minute. Batches of 50, each journaled as its own call."""
        results: list = []
        for i in range(0, len(actions), A.MAX_BATCH):
            batch = list(actions[i: i + A.MAX_BATCH])
            self._check(batch)
            req = {"at": self.now, "actions": batch}
            part = self._call("act", req, lambda r: self.live.act(r["actions"]), self._recover_act)
            self._take_results(batch, part)
            results += part
        return results

    def advance(self, until: Sequence[str], max: int, actions: Sequence[dict] = ()) -> dict:
        """Applies the actions at the current minute, then moves the clock to the next event of a kind in
        `until`, but not past `max`. The same requests as the kit's World.advance."""
        actions = list(actions)
        early, last = actions[: -A.MAX_BATCH], actions[-A.MAX_BATCH:]
        results = self.act(early) if early else []
        if last:
            self._check(last)
        req = {"at": self.now, "untilEvent": list(until), "max": max, "actions": last}
        step = self._call("advance", req, self._live_advance, self._recover_advance)
        self._take_results(last, step["results"])
        self.now = step["now"]
        if step["events"]:
            self.last_seq = step["events"][-1]["seq"]
        self.on_events(step["events"])
        self.on_clock(step["now"])
        return {"now": step["now"], "events": step["events"], "results": results + step["results"]}

    # ---- plumbing ----------------------------------------------------------------------------------

    def _check(self, batch: list) -> None:
        if self.validate:
            found = A.batch_errors(batch)
            if found:
                raise A.InvalidAction({"type": "batch"}, found)

    def _take_results(self, actions: list, results: list) -> None:
        for action, result in zip(actions, results):
            if action["type"] == "post" and result.get("ok") is True:
                self.known_gigs.add(result["id"])
        self.on_results(actions, results)

    def _call(self, op: str, req: dict, live_fn: Callable[[dict], Any], recover_fn: Callable[[str, dict], Any]) -> Any:
        req = normal(req)
        if self.replaying:
            call = self.journal.calls[self.pos]
            if call.op != op or call.req != req:
                raise ReplayDivergence(f"call {call.n}: recorded {call.op} {str(call.req)[:300]} but the desk now makes {op} {str(req)[:300]}")
            self.pos += 1
            if call.resp is not None:
                self.stats["replayed"] += 1
                return call.resp
            resp = normal(recover_fn(op, req))  # the call that was in flight when the desk stopped
            self.journal.answer(call.n, resp)
            return resp
        n = self.journal.begin(op, req)
        self.pos += 1
        resp = normal(live_fn(req))
        self.journal.answer(n, resp)
        self.stats["live"] += 1
        return resp

    def _live_advance(self, req: dict) -> dict:
        body = {"untilEvent": req["untilEvent"], "max": req["max"]}
        if req["actions"]:
            body["actions"] = req["actions"]
        step = self.live.client.call("POST", f"/v1/worlds/{self.live.id}/advance", body)
        events = self._fill_gaps([e for e in step["events"] if e["seq"] > self.last_seq], step["now"])
        return {"now": step["now"], "events": events, "results": step.get("results", [])}

    def _fill_gaps(self, events: list, now: int) -> list:
        """An answer whose sequence numbers skip is missing events: during server incidents (14 Nov) advance
        answers dropped events that the world's log holds, an order_won among them. Clean weeks never skip
        (0 gaps in 179,047 events), so a skip is the alarm; the full list then comes from GET /events."""
        seqs = [self.last_seq] + [e["seq"] for e in events]
        if all(b == a + 1 for a, b in zip(seqs, seqs[1:])):
            return events
        self.stats["gaps_filled"] += 1
        return [e for e in self.live.events(after=self.last_seq) if e["seq"] > self.last_seq and e["at"] <= now]

    # ---- recovery of the call in flight --------------------------------------------------------------

    def _recover_read(self, op: str, req: dict) -> Any:
        self.stats["recovered_read"] += 1
        return self.live.snapshot() if op == "snapshot" else self.live.score()

    def _fresh_gigs(self, snap: dict, at: int) -> list:
        return [g for g in snap["gigs"] if g["postedAt"] == at and g["id"] not in self.known_gigs]

    def _posted(self, actions: list, snap: dict, at: int) -> Optional[list]:
        """Results for a batch that the world applied, or None if it shows no sign of it. A batch without
        posts leaves no sign; it is sent again (quotes, reprices and withdraws are safe to repeat)."""
        if not any(a["type"] == "post" for a in actions) or not self._fresh_gigs(snap, at):
            return None
        return self._rebuilt_results(actions, snap, at)

    def _rebuilt_results(self, actions: list, snap: dict, at: int) -> list:
        """The answer of a batch that the world applied: each post gets the gig with its stops posted at that minute."""
        fresh = self._fresh_gigs(snap, at)
        results, taken = [], set()
        for action in actions:
            if action["type"] != "post":
                results.append({"ok": True, "id": "recovered"})
                continue
            match = next((g for g in fresh if g["id"] not in taken and stops_key(g["stops"]) == stops_key(action["stops"])), None)
            if match:
                taken.add(match["id"])
                results.append({"ok": True, "id": match["id"]})
            else:
                results.append({"ok": False, "reason": "recovered: the world shows no gig for this post"})
        return results

    def _recover_act(self, op: str, req: dict) -> list:
        snap = self.live.snapshot()
        results = self._posted(req["actions"], snap, req["at"])
        if results is not None:
            self.stats["recovered_applied"] += 1
            return results
        self.stats["recovered_resent"] += 1
        return self.live.act(req["actions"])

    def _recover_advance(self, op: str, req: dict) -> dict:
        snap = self.live.snapshot()
        events = [e for e in self.live.events(after=self.last_seq) if e["seq"] > self.last_seq]
        moved = snap["now"] != req["at"] or bool(events)
        posted = self._posted(req["actions"], snap, req["at"]) if req["actions"] else None
        if moved or posted is not None:
            self.stats["recovered_applied"] += 1
            results = self._rebuilt_results(req["actions"], snap, req["at"])
            return {"now": snap["now"], "events": events, "results": results, "recovered": True}
        self.stats["recovered_resent"] += 1
        return self._live_advance(req)
