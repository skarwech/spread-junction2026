"""An append-only journal of every call the desk makes to a world, and its answer.

One JSON object per line: first `{"n", "op", "req"}` before the call goes out, then `{"n", "resp"}` once the
answer is in. A desk killed at any instant leaves a journal whose calls all have answers except perhaps the
last: that call was in flight, and `WorldIO` recovers it from the world's state. A line cut off by the kill
can only be the last one; it is dropped on load.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


class CorruptJournal(RuntimeError):
    pass


@dataclass(frozen=True)
class Call:
    n: int
    op: str
    req: Any
    resp: Optional[Any]  # None while in flight


def normal(value: Any) -> Any:
    """The value as it reads back from JSON (tuples become lists), so a live request compares equal to its record."""
    return json.loads(json.dumps(value))


def load(path: Path) -> list[Call]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records = []
    for i, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except ValueError:
            if i == len(lines) - 1:
                break  # cut off by a kill mid-write: the call it began never went out, or its answer is recovered
            raise CorruptJournal(f"{path}: line {i + 1} does not parse")
    calls: list[Call] = []
    for rec in records:
        if "op" in rec:
            if calls and calls[-1].resp is None:
                raise CorruptJournal(f"{path}: call {rec['n']} starts while call {calls[-1].n} has no answer")
            if rec["n"] != len(calls):
                raise CorruptJournal(f"{path}: call {rec['n']} out of order")
            calls.append(Call(rec["n"], rec["op"], rec["req"], None))
        else:
            if not calls or calls[-1].n != rec["n"] or calls[-1].resp is not None:
                raise CorruptJournal(f"{path}: answer {rec['n']} has no open call")
            last = calls[-1]
            calls[-1] = Call(last.n, last.op, last.req, rec["resp"])
    return calls


class Journal:
    """Appends records; every line is flushed to the OS before the call it describes goes out."""

    def __init__(self, path: Path, fsync: bool = False):
        self.path, self.fsync = path, fsync
        path.parent.mkdir(parents=True, exist_ok=True)
        self.calls = load(path)
        self._repair_tail()
        self._file = open(path, "a", encoding="utf-8")

    def _repair_tail(self) -> None:
        """Cuts a cut-off last line in place, so the next append starts on a fresh line. One ftruncate: a kill
        here leaves either the old file or the repaired one, never a shorter prefix (review finding, 14 Nov)."""
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        if data and not data.endswith(b"\n"):
            with open(self.path, "r+b") as f:
                f.truncate(data.rfind(b"\n") + 1)
                f.flush()
                os.fsync(f.fileno())

    def _write(self, record: dict) -> None:
        self._file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._file.flush()
        if self.fsync:
            os.fsync(self._file.fileno())

    def begin(self, op: str, req: Any) -> int:
        n = len(self.calls)
        self._write({"n": n, "op": op, "req": req})
        self.calls.append(Call(n, op, normal(req), None))
        return n

    def answer(self, n: int, resp: Any) -> None:
        call = self.calls[n]
        if call.resp is not None:
            raise CorruptJournal(f"call {n} already has an answer")
        self._write({"n": n, "resp": resp})
        self.calls[n] = Call(call.n, call.op, call.req, normal(resp))

    def close(self) -> None:
        self._file.close()


def write_atomic(path: Path, text: str) -> None:
    """Writes a small file so that a kill leaves either the old content or the new, never a truncated file."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
