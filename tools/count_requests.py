"""Runs the unmodified kit starter on a practice world and counts its API requests by route.

    python -m tools.count_requests --level 8 --seed spread-1

It wraps Client.call only to count: the starter's advance stops and actions are unchanged, so the
week must match the plain CLI run to the cent. Prints `REQUESTS <n> <json by route>` at the end.
Only --level and --seed are accepted (no abbreviations), and the wrapper refuses any request that
would create a ranking run or touch the final.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any

from spread import client, starter

WORLD_ID = re.compile(r"/v1/worlds/[^/?]+")
_original_call = client.Client.call
_counts: Counter = Counter()


class Refused(RuntimeError):
    """A request that G0 must never send."""


def _counted_call(self: client.Client, method: str, path: str, body: Any = None, actions: int = 0) -> Any:
    bare = path.split("?")[0]
    if bare.startswith("/v1/final") or (method == "POST" and bare == "/v1/worlds" and isinstance(body, dict) and body.get("board")):
        raise Refused(f"refused {method} {bare}: G0 plays practice worlds only")
    _counts[f"{method} {WORLD_ID.sub('/v1/worlds/{id}', bare)}"] += 1
    return _original_call(self, method, path, body, actions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--seed")
    args = parser.parse_args()  # --board, --boa, --final, --fin: argparse error
    client.Client.call = _counted_call
    sys.argv = ["spread-starter", "--level", str(args.level)] + (["--seed", args.seed] if args.seed is not None else [])
    try:
        starter.main()
    finally:
        print(f"REQUESTS {sum(_counts.values())} {json.dumps(dict(_counts), sort_keys=True)}", flush=True)


if __name__ == "__main__":
    main()
