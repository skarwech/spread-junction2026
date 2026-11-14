"""The server-determinism canary: the kit's starter on seed spread-1, level 8, must print the handbook's week to
the cent. Run it alongside an experiment; if it does not match, the server had an incident during the window
and the experiment's runs may not reproduce (seen on 14 Nov: identical requests, different answers, while the
server timed out). Runs the kit's own CLI, so none of our code is involved.
"""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from tools.g0 import ROOT, assess_level, parse_transcript, starter_command, team_env

HANDBOOK = ROOT / "expected" / "handbook_L8_spread-1.txt"


class Canary:
    def __init__(self, log: Path):
        self.log = log
        self.result: dict = {}
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "Canary":
        self._thread.start()
        return self

    def _run(self) -> None:
        cmd = starter_command(str(ROOT / ".venv" / "bin" / "spread-starter"), 8)
        with open(self.log, "w", encoding="utf-8") as out:
            code = subprocess.run(cmd, cwd=ROOT, env=team_env(), stdout=out, stderr=subprocess.STDOUT).returncode
        expected = parse_transcript(HANDBOOK.read_text(encoding="utf-8"))
        got = parse_transcript(self.log.read_text(encoding="utf-8"))
        assessed = assess_level(8, got, code, expected.days[-1].margin_cents, expected)
        self.result = {"exit": code, "match": assessed["match"], "endMarginCents": assessed["end"]["actual"], "worldId": got.world_id}

    def wait(self) -> dict:
        self._thread.join()
        return self.result
