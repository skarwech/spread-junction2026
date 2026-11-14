"""The kit's Client, made safe for a flaky network.

The kit resends a request when a kept-alive connection breaks (spread/client.py:170), assuming "the request
never arrived". That holds when the break comes while sending, but not when it comes while waiting for the
answer: then the server may have applied the request. On 14 Nov, on this machine's unstable network, that resend
applied advances twice: duplicate gigs for the same car (g354/g355), a clock moved further, and the first
answer's events lost (seq gaps). SafeClient resends only reads, and POSTs that broke while being sent; any other
break becomes `Unreachable`, which WorldIO recovers by checking the world's snapshot and event log.
"""
from __future__ import annotations

import http.client
from typing import Any, Optional

from spread.client import Client, Unreachable


class SafeClient(Client):
    """`timeout`: seconds without a byte before a request counts as lost. 20 (the kit's) for the desk's main
    calls; 2 for quotes and the clock, which are safe to repeat and must not wait past a 4.5 s window."""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None, timeout: float = 20.0):
        super().__init__(url, key)
        self.timeout = timeout

    def _new_connection(self) -> Any:
        kind = http.client.HTTPSConnection if self._parts.scheme == "https" else http.client.HTTPConnection
        return kind(self._parts.netloc, timeout=self.timeout)

    def _send(self, method: str, path: str, payload: Optional[bytes], headers: dict):
        while True:
            reused = self._connection is not None
            if self._connection is None:
                self._connection = self._new_connection()
            sent = False
            try:
                self._connection.request(method, self._parts.path + path, payload, headers)
                sent = True
                response = self._connection.getresponse()
                return response.status, response.headers, response.read()
            except BaseException as error:
                self._connection.close()
                self._connection = None
                broken = isinstance(error, (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected))
                safe_to_resend = method == "GET" or not sent
                if reused and broken and safe_to_resend:
                    continue
                if isinstance(error, (OSError, http.client.HTTPException)):
                    what = "the answer was lost; the request may have been applied" if sent else "the request did not leave"
                    raise Unreachable(0, f"Cannot reach {self.url} ({what}): {error}") from error
                raise
