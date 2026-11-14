"""The request counter must never be able to start a ranking run or touch the final. No network here."""
import sys

import pytest

import tools.count_requests as cr


@pytest.fixture
def no_starter(monkeypatch):
    calls = []
    monkeypatch.setattr(cr.starter, "main", lambda: calls.append(list(sys.argv)))
    monkeypatch.setattr(cr.client.Client, "call", cr._original_call)  # undo the wrapper main() installs
    return calls


@pytest.mark.parametrize("flag", ["--board", "--boa", "--b", "--final", "--fin"])
def test_board_and_final_flags_are_rejected_before_the_starter_runs(monkeypatch, no_starter, flag):
    monkeypatch.setattr(sys, "argv", ["count_requests", "--level", "8", flag])
    with pytest.raises(SystemExit) as stop:
        cr.main()
    assert stop.value.code == 2
    assert no_starter == []


def test_level_and_seed_are_passed_through_unchanged(monkeypatch, no_starter):
    monkeypatch.setattr(sys, "argv", ["count_requests", "--level", "7", "--seed", "spread-1"])
    cr.main()
    assert no_starter == [["spread-starter", "--level", "7", "--seed", "spread-1"]]


@pytest.mark.parametrize("method, path, body", [
    ("POST", "/v1/worlds", {"level": 8, "board": True}),
    ("GET", "/v1/final", None),
    ("GET", "/v1/final?x=1", None),
])
def test_wrapper_refuses_ranking_runs_and_the_final(monkeypatch, method, path, body):
    sent = []
    monkeypatch.setattr(cr, "_original_call", lambda *a: sent.append(a))
    with pytest.raises(cr.Refused):
        cr._counted_call(object(), method, path, body)
    assert sent == []


def test_wrapper_counts_and_passes_practice_requests_through(monkeypatch):
    sent = []
    monkeypatch.setattr(cr, "_original_call", lambda self, m, p, b, a: sent.append((m, p, b, a)) or "ok")
    monkeypatch.setattr(cr, "_counts", cr.Counter())
    assert cr._counted_call(object(), "POST", "/v1/worlds", {"level": 8, "board": False}) == "ok"
    assert cr._counted_call(object(), "POST", "/v1/worlds/wabc/advance", {"to": 5}, 3) == "ok"
    assert sent == [("POST", "/v1/worlds", {"level": 8, "board": False}, 0), ("POST", "/v1/worlds/wabc/advance", {"to": 5}, 3)]
    assert dict(cr._counts) == {"POST /v1/worlds": 1, "POST /v1/worlds/{id}/advance": 1}
