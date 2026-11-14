"""SafeClient never sends a POST twice: a connection that breaks after the request left may have delivered it."""
import pytest
from spread.client import Unreachable

from desk.client import SafeClient


class Response:
    status, headers = 200, {}

    def read(self):
        return b"{}"


class Connection:
    """Fails as scripted: 'send' breaks while sending, 'answer' breaks after the request was sent."""

    def __init__(self, script, log):
        self.script, self.log = script, log

    def request(self, method, path, payload, headers):
        self.log.append((method, path))
        if self.script and self.script[0] == "send":
            self.script.pop(0)
            raise BrokenPipeError("closed while idle")

    def getresponse(self):
        if self.script and self.script[0] == "answer":
            self.script.pop(0)
            raise ConnectionResetError("reset after the request left")
        return Response()

    def close(self):
        pass


def client_with(script):
    c = SafeClient("https://example.test", "key")
    log = []
    c._new_connection = lambda: Connection(script, log)
    c._connection = Connection(script, log)  # a kept-alive connection, as after a first request
    return c, log


def test_a_post_whose_answer_was_lost_is_not_sent_again():
    c, log = client_with(["answer"])
    with pytest.raises(Unreachable):
        c._send("POST", "/v1/worlds/w/advance", b"{}", {})
    assert log == [("POST", "/v1/worlds/w/advance")]


def test_a_post_that_never_left_is_sent_again_once():
    c, log = client_with(["send"])
    status, _, _ = c._send("POST", "/v1/worlds/w/actions", b"[]", {})
    assert status == 200 and len(log) == 2


def test_a_read_is_retried_after_a_lost_answer():
    c, log = client_with(["answer"])
    status, _, _ = c._send("GET", "/v1/worlds/w", None, {})
    assert status == 200 and len(log) == 2
