"""The live desk's guards, without a network."""
from spread.client import SpreadError

from desk import actions as A
from desk import live
from desk.live import LiveIO, supervised


class Log:
    def __init__(self):
        self.lines = []

    def __call__(self, kind, **fields):
        self.lines.append((kind, fields))


class StreamWorld:
    """Connection 1 delivers 0, 1 then breaks; connection 2 (after=1) skips 2 and delivers 3."""

    def __init__(self):
        self.connections, self.acted = [], []

    def stream(self, after, idle):
        self.connections.append(after)
        if len(self.connections) == 1:
            yield {"seq": 0, "at": 1, "kind": "forecast"}
            yield {"seq": 1, "at": 2, "kind": "forecast"}
            raise SpreadError(429, "too many requests")
        yield {"seq": 1, "at": 2, "kind": "forecast"}  # a repeat after reconnecting
        yield {"seq": 3, "at": 4, "kind": "forecast"}

    def events(self, after=-1):
        return [{"seq": s, "at": s + 1, "kind": "forecast"} for s in range(after + 1, 4)]

    def act(self, batch):
        self.acted.append(batch)
        return [{"ok": True, "id": f"x{i}"} for i, _ in enumerate(batch)]


def test_stream_reconnects_from_the_last_seq_skips_repeats_and_fills_holes(monkeypatch):
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    world, log = StreamWorld(), Log()
    got = [e["seq"] for e in supervised(world, -1, 1.0, log) if e is not None]
    assert got == [0, 1, 2, 3]
    assert world.connections == [-1, 1]
    assert [k for k, _ in log.lines] == ["stream_error", "gap", "stream_end"]


def test_an_invalid_action_is_dropped_and_its_batch_still_goes():
    world, log = StreamWorld(), Log()
    io = LiveIO(world, log)
    good = A.quote("r1", {"next_day": 100})
    bad = {"type": "quote", "requestId": "r2", "prices": {"next_day": 1.5}}
    results = io.act([good, bad, good])
    assert world.acted == [[good, good]]
    assert results[0]["ok"] and results[2]["ok"] and results[1]["ok"] is False
    assert io.dropped == 1 and io.sent == 2


def test_quote_thread_batches_skips_closed_windows_and_never_blocks_the_desk():
    import threading
    from desk.live import QuoteSender
    gate = threading.Event()

    class SlowWorld(StreamWorld):
        def act(self, batch):
            gate.wait(5)  # the first request hangs until released
            return super().act(batch)

    world, log = SlowWorld(), Log()
    respond_by = {"r1": 100, "r2": 100, "r3": 5, "r4": 100}
    sender = QuoteSender(world, log, respond_by.get, lambda: 10)
    io = LiveIO(world, log, sender)
    io.act([A.quote("r1", {"next_day": 1})])           # goes out at once, then hangs
    import time
    deadline = time.time() + 5
    while sender._queue and time.time() < deadline:     # wait until the thread has taken r1
        time.sleep(0.01)
    out = io.act([A.quote(r, {"next_day": 1}) for r in ("r2", "r3", "r4")])  # queued while r1 is in flight
    assert all(r == {"ok": True, "id": "queued"} for r in out)   # the desk did not wait
    gate.set()
    sender.close()
    assert [[q["requestId"] for q in b] for b in world.acted] == [["r1"], ["r2", "r4"]]  # r3's window closed at 5
    assert sender.skipped == 1 and sender.sent == 3


def test_quote_thread_retries_a_lost_batch_and_survives_any_error(monkeypatch):
    from spread.client import Unreachable
    from desk.live import QuoteSender
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    failures = [Unreachable(0, "reset"), ValueError("odd answer")]

    class FlakyWorld(StreamWorld):
        def act(self, batch):
            if failures:
                raise failures.pop(0)
            return super().act(batch)

    world, log = FlakyWorld(), Log()
    sender = QuoteSender(world, log, lambda rid: 100, lambda: 10)
    sender.put(A.quote("r1", {"next_day": 1}))
    sender.close()
    assert [[q["requestId"] for q in b] for b in world.acted] == [["r1"]] and sender.sent == 1
    assert [k for k, _ in log.lines].count("quote_error") == 2


def test_a_silent_stream_is_detected_by_the_probe_and_reopened(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(live.time, "time", lambda: clock["t"])
    monkeypatch.setattr(live.time, "sleep", lambda s: None)

    class SilentWorld(StreamWorld):
        def stream(self, after, idle):
            self.connections.append(after)
            if len(self.connections) == 1:
                yield {"seq": 0, "at": 1, "kind": "forecast"}
                while True:  # half-open: no error, no events
                    clock["t"] += 1.0
                    yield None
            yield {"seq": 1, "at": 2, "kind": "forecast"}

    world, log = SilentWorld(), Log()
    probes = []
    got = []
    for e in supervised(world, -1, 1.0, log, probe=lambda after: probes.append(after) or [{"seq": after + 1}], silence=10.0):
        if e is not None:
            got.append(e["seq"])
        if len(got) == 2:
            break
    assert got == [0, 1] and world.connections == [-1, 0] and probes == [0]
    assert "stream_silent" in [k for k, _ in log.lines]


def test_safe_client_timeout_is_configurable():
    from desk.client import SafeClient
    assert SafeClient("https://example.test", "k", timeout=2.0)._new_connection().timeout == 2.0
    assert SafeClient("https://example.test", "k")._new_connection().timeout == 20.0
