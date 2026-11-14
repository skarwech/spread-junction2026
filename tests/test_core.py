"""The journal and WorldIO without a network: replay, divergence, and recovery of the call in flight."""

import pytest

from desk import actions as A
from desk.journal import CorruptJournal, Journal, load
from desk.state import State
from desk.worldio import ReplayDivergence, WorldIO


class FakeClient:
    def __init__(self, world):
        self.world = world

    def call(self, method, path, body=None, actions=0):
        assert path.endswith("/advance")
        return self.world.do_advance(body)


class FakeWorld:
    """A tiny deterministic world: posts become gigs, advance moves the clock by 10 and emits one event."""

    def __init__(self):
        self.id, self.now, self.gigs, self.log, self.calls = "wfake", 0, [], [], []
        self.client = FakeClient(self)

    def _apply(self, actions):
        results = []
        for a in actions:
            if a["type"] == "post":
                gid = f"g{len(self.gigs)}"
                self.gigs.append({"id": gid, "postedAt": self.now, "stops": a["stops"]})
                results.append({"ok": True, "id": gid})
            else:
                results.append({"ok": True, "id": "x"})
        return results

    def snapshot(self):
        self.calls.append("snapshot")
        return {"now": self.now, "endsAt": 100, "gigs": list(self.gigs)}

    def score(self):
        self.calls.append("score")
        return {"marginCents": 0}

    def act(self, actions):
        self.calls.append("act")
        return self._apply(actions)

    def events(self, after=-1):
        self.calls.append("events")
        return [e for e in self.log if e["seq"] > after]

    def do_advance(self, body):
        self.calls.append("advance")
        results = self._apply(body.get("actions", []))
        self.now += 10
        self.log.append({"seq": len(self.log), "at": self.now, "kind": "forecast"})
        return {"now": self.now, "events": [self.log[-1]], "results": results}


def post(order="o1"):
    return A.post([A.stop(order, 0, "pickup"), A.stop(order, 0, "delivery")], False, False, [A.fee_step(0, 100)])


def script(io):
    io.snapshot()
    io.advance(["forecast"], 100, [post("o1")])
    io.act([post("o2"), A.quote("r9", {"next_day": 5})])
    io.advance(["forecast"], 100, [])
    return io.score()


def test_replay_makes_no_calls_and_gives_the_same_answers(tmp_path):
    world = FakeWorld()
    first = WorldIO(world, Journal(tmp_path / "j.jsonl"))
    script(first)
    calls_before = list(world.calls)
    again = WorldIO(world, Journal(tmp_path / "j.jsonl"))
    script(again)
    assert world.calls == calls_before
    assert again.stats["replayed"] == 5 and again.stats["live"] == 0
    assert again.known_gigs == first.known_gigs and again.last_seq == first.last_seq


def test_a_different_decision_on_replay_is_caught(tmp_path):
    world = FakeWorld()
    script(WorldIO(world, Journal(tmp_path / "j.jsonl")))
    io = WorldIO(world, Journal(tmp_path / "j.jsonl"))
    io.snapshot()
    with pytest.raises(ReplayDivergence):
        io.advance(["forecast"], 100, [post("other")])


def _cut_after(path, n_lines):
    lines = path.read_text().splitlines(keepends=True)
    path.write_text("".join(lines[:n_lines]))


@pytest.mark.parametrize("applied", [True, False])
def test_advance_in_flight_is_recovered_once(tmp_path, applied):
    world = FakeWorld()
    path = tmp_path / "j.jsonl"
    io = WorldIO(world, Journal(path))
    io.snapshot()
    io.advance(["forecast"], 100, [post("o1")])
    # the desk is killed after writing the second advance's request; the world did or did not get it
    Journal(path).begin("advance", {"at": io.now, "untilEvent": ["forecast"], "max": 100, "actions": [post("o2")]})
    if applied:
        world.do_advance({"actions": [post("o2")]})
    gigs_before = len(world.gigs)
    io2 = WorldIO(world, Journal(path))
    io2.snapshot()
    io2.advance(["forecast"], 100, [post("o1")])
    step = io2.advance(["forecast"], 100, [post("o2")])
    assert len(world.gigs) == gigs_before + (0 if applied else 1)  # never posted twice
    assert step["results"][0] == {"ok": True, "id": "g1"}
    assert io2.stats["recovered_applied" if applied else "recovered_resent"] == 1
    assert load(path)[-1].resp is not None


@pytest.mark.parametrize("applied", [True, False])
def test_act_in_flight_is_recovered_once(tmp_path, applied):
    world = FakeWorld()
    path = tmp_path / "j.jsonl"
    io = WorldIO(world, Journal(path))
    io.snapshot()
    Journal(path).begin("act", {"at": 0, "actions": [post("o1")]})
    if applied:
        world.act([post("o1")])
    io2 = WorldIO(world, Journal(path))
    io2.snapshot()
    assert io2.act([post("o1")]) == [{"ok": True, "id": "g0"}]
    assert len(world.gigs) == 1


def test_a_line_cut_off_by_a_kill_is_dropped_and_the_file_repaired(tmp_path):
    path = tmp_path / "j.jsonl"
    io = WorldIO(FakeWorld(), Journal(path))
    io.snapshot()
    with open(path, "a") as f:
        f.write('{"n": 1, "op": "adv')
    j = Journal(path)
    assert len(j.calls) == 1 and path.read_text().endswith("\n")


def test_a_corrupt_line_in_the_middle_stops_the_desk(tmp_path):
    path = tmp_path / "j.jsonl"
    path.write_text('{"n":0,"op":"score","req":{}}\nnot json\n{"n":0,"resp":{}}\n')
    with pytest.raises(CorruptJournal):
        load(path)


def test_invalid_actions_never_leave(tmp_path):
    world = FakeWorld()
    io = WorldIO(world, Journal(tmp_path / "j.jsonl"))
    io.snapshot()
    with pytest.raises(A.InvalidAction):
        io.advance(["forecast"], 100, [{"type": "quote", "requestId": "r1", "prices": {"next_day": 1.5}}])
    assert "advance" not in world.calls


def test_state_ignores_repeated_events_and_sums_the_ledger():
    s = State()
    line = {"seq": 1, "at": 5, "kind": "ledger", "line": {"at": 5, "kind": "driver_fee", "cents": -700, "orderId": None, "gigId": "g1", "detail": ""}}
    s.apply_events([line, line, {**line, "seq": 2}])
    assert s.margin_cents == -1400 and s.duplicates == 1


def test_tail_repair_truncates_in_place_and_never_rewrites(tmp_path, monkeypatch):
    path = tmp_path / "j.jsonl"
    io = WorldIO(FakeWorld(), Journal(path))
    io.snapshot()
    good = path.read_bytes()
    with open(path, "ab") as f:
        f.write(b'{"n": 1, "op": "adv')
    from pathlib import Path as _P
    monkeypatch.setattr(_P, "write_text", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rewrote the journal")))
    Journal(path)
    assert path.read_bytes() == good


def test_write_atomic_replaces_whole_file(tmp_path):
    from desk.journal import write_atomic
    target = tmp_path / "meta.json"
    write_atomic(target, '{"a": 1}')
    write_atomic(target, '{"a": 2}')
    assert target.read_text() == '{"a": 2}' and not (tmp_path / "meta.json.tmp").exists()


def _ledger(seq, kind, order, cents=100):
    return {"seq": seq, "at": 2365, "kind": "ledger", "line": {"at": 2365, "kind": kind, "cents": cents, "orderId": order, "gigId": None, "detail": ""}}


def test_trust_follows_the_account_line_order_not_order_ids():
    s = State()
    for oid in ("R00039", "R00047"):
        s.apply_events([{"seq": len(s.ledger) + (10 if oid == "R00047" else 5), "at": 1, "kind": "order_won",
                         "order": {"id": oid, "dealerId": "D02", "deadline": 9999, "deliveredAt": [None], "legs": [{}]}}])
    s.apply_events([_ledger(20, "revenue", "R00047"), _ledger(21, "late_refund", "R00047", -10), _ledger(22, "revenue", "R00039")])
    assert s.trust() == {"D02": 1}  # late halves 0 -> 0, then the on-time order adds 1


def test_overdue_counts_from_the_world_clock():
    s = State()
    s.apply_events([{"seq": 1, "at": 10, "kind": "order_won", "order": {"id": "o", "dealerId": "d", "deadline": 100, "deliveredAt": [None], "legs": [{}]}}])
    assert s.summary()["overdue"] == 0
    s.set_clock(200)
    assert s.summary()["overdue"] == 1


class GappyWorld(FakeWorld):
    """Like the real server during an incident: an advance answer that skips events the log holds."""

    def do_advance(self, body):
        self.calls.append("advance")
        results = self._apply(body.get("actions", []))
        self.now += 10
        for _ in range(3):
            self.log.append({"seq": len(self.log), "at": self.now, "kind": "forecast"})
        return {"now": self.now, "events": [self.log[-1]], "results": results}  # drops the first two of three


def test_a_gap_in_an_advance_answer_is_filled_from_the_event_log(tmp_path):
    world = GappyWorld()
    io = WorldIO(world, Journal(tmp_path / "j.jsonl"))
    seen = []
    io.on_events = seen.extend
    io.snapshot()
    step = io.advance(["forecast"], 100, [])
    assert [e["seq"] for e in step["events"]] == [0, 1, 2]
    assert [e["seq"] for e in seen] == [0, 1, 2] and io.stats["gaps_filled"] == 1
    replay = WorldIO(world, Journal(tmp_path / "j.jsonl"))
    replay.snapshot()
    assert [e["seq"] for e in replay.advance(["forecast"], 100, [])["events"]] == [0, 1, 2]  # the journal keeps the repaired answer


def test_a_contiguous_answer_costs_no_extra_call(tmp_path):
    world = FakeWorld()
    io = WorldIO(world, Journal(tmp_path / "j.jsonl"))
    io.snapshot()
    io.advance(["forecast"], 100, [])
    io.advance(["forecast"], 100, [])
    assert "events" not in world.calls and io.stats["gaps_filled"] == 0
