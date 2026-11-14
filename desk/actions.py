"""Action builders and the pre-flight validator.

Every action the desk sends is built here and checked before it leaves: one action that does not parse
fails the whole request with 400, including the `advance` it rides on (API.md:151). Two layers:

- `schema_errors`: the server's contract, `components.schemas.Action` in openapi.json, a little stricter
  (cents and minutes must be Python ints, never floats or bools).
- `rule_errors`: world rules the schema does not check but the server enforces or the rules state
  (RULES.md:47 at least one price; RULES.md:64 steps in time order, fees never fall).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

MAX_INT = 9007199254740991  # 2**53 - 1, the schema's maximum for cents and minutes
OPTIONS = ("same_day", "next_day", "within_3_days")
STOP_KINDS = ("pickup", "delivery")
MAX_STEPS = 48
MAX_BATCH = 50


class InvalidAction(ValueError):
    def __init__(self, action: Mapping[str, Any], errors: list[str]):
        super().__init__(f"{action.get('type', '?')}: " + "; ".join(errors))
        self.action, self.errors = action, errors


# ---- checks ------------------------------------------------------------------------------------------

def _int(v: Any, path: str, low: int, out: list[str]) -> None:
    if not isinstance(v, int) or isinstance(v, bool):
        out.append(f"{path}: must be an integer, got {type(v).__name__}")
    elif not low <= v <= MAX_INT:
        out.append(f"{path}: {v} is outside {low}..{MAX_INT}")


def _id(v: Any, path: str, out: list[str]) -> None:
    if not isinstance(v, str) or not 1 <= len(v) <= 64:
        out.append(f"{path}: must be a string of 1 to 64 characters")


def _bool(v: Any, path: str, out: list[str]) -> None:
    if not isinstance(v, bool):
        out.append(f"{path}: must be true or false")


def _object(v: Any, path: str, required: Sequence[str], out: list[str]) -> bool:
    if not isinstance(v, dict):
        out.append(f"{path or 'action'}: must be an object")
        return False
    missing = [k for k in required if k not in v]
    out.extend(f"{path}.{k}: required" if path else f"{k}: required" for k in missing)
    return not missing


def _schedule(v: Any, path: str, out: list[str]) -> None:
    if not isinstance(v, list) or not 1 <= len(v) <= MAX_STEPS:
        out.append(f"{path}: must hold 1 to {MAX_STEPS} steps")
        return
    for i, step in enumerate(v):
        if _object(step, f"{path}[{i}]", ("at", "feeCents"), out):
            _int(step["at"], f"{path}[{i}].at", 0, out)
            _int(step["feeCents"], f"{path}[{i}].feeCents", 1, out)


def _stops(v: Any, path: str, out: list[str]) -> None:
    if not isinstance(v, list) or len(v) < 2:
        out.append(f"{path}: must hold at least 2 stops")
        return
    for i, s in enumerate(v):
        p = f"{path}[{i}]"
        if not _object(s, p, ("orderId", "leg", "kind"), out):
            continue
        _id(s["orderId"], f"{p}.orderId", out)
        if s["leg"] not in (0, 1) or isinstance(s["leg"], bool) or not isinstance(s["leg"], int):
            out.append(f"{p}.leg: must be 0 or 1")
        if s["kind"] not in STOP_KINDS:
            out.append(f"{p}.kind: must be pickup or delivery")
        if "window" in s and _object(s["window"], f"{p}.window", ("from", "to"), out):
            _int(s["window"]["from"], f"{p}.window.from", 0, out)
            _int(s["window"]["to"], f"{p}.window.to", 0, out)
        for flag in ("withPlates", "withCharging"):
            if flag in s:
                _bool(s[flag], f"{p}.{flag}", out)


def schema_errors(action: Any) -> list[str]:
    """What the server's schema would refuse (plus floats and bools where it wants integers)."""
    out: list[str] = []
    if not _object(action, "", ("type",), out):
        return out
    kind = action["type"]
    if kind == "quote" and _object(action, "", ("requestId", "prices"), out):
        _id(action["requestId"], "requestId", out)
        prices = action["prices"]
        if not isinstance(prices, dict):
            out.append("prices: must be an object")
        else:
            for option, cents in prices.items():
                if option not in OPTIONS:
                    out.append(f"prices.{option}: not an option kind")
                _int(cents, f"prices.{option}", 1, out)
    elif kind == "post" and _object(action, "", ("stops", "audience", "schedule"), out):
        _stops(action["stops"], "stops", out)
        if _object(action["audience"], "audience", ("experienced", "manualLicence"), out):
            _bool(action["audience"]["experienced"], "audience.experienced", out)
            _bool(action["audience"]["manualLicence"], "audience.manualLicence", out)
        _schedule(action["schedule"], "schedule", out)
    elif kind == "offer" and _object(action, "", ("gigId", "driverId", "feeCents"), out):
        _id(action["gigId"], "gigId", out)
        _id(action["driverId"], "driverId", out)
        _int(action["feeCents"], "feeCents", 1, out)
    elif kind == "reprice" and _object(action, "", ("gigId", "schedule"), out):
        _id(action["gigId"], "gigId", out)
        _schedule(action["schedule"], "schedule", out)
    elif kind in ("withdraw", "release") and _object(action, "", ("gigId",), out):
        _id(action["gigId"], "gigId", out)
    elif kind not in ("quote", "post", "offer", "reprice", "withdraw", "release"):
        out.append(f"type: unknown action type {kind!r}")
    return out


def rule_errors(action: Mapping[str, Any]) -> list[str]:
    """World rules that parse but would be refused or are forbidden (only meaningful on schema-valid actions)."""
    out: list[str] = []
    if action["type"] == "quote" and not action["prices"]:
        out.append("prices: a quote needs at least one price (RULES.md:47)")
    schedule = action.get("schedule") if action["type"] in ("post", "reprice") else None
    if schedule:
        times = [s["at"] for s in schedule]
        fees = [s["feeCents"] for s in schedule]
        if times != sorted(times):
            out.append("schedule: steps must be in time order (RULES.md:64)")
        if any(b < a for a, b in zip(fees, fees[1:])):
            out.append("schedule: no fee may be lower than the one before (RULES.md:64)")
    for i, s in enumerate(action.get("stops", []) if action["type"] == "post" else []):
        w = s.get("window")
        if w and w["from"] > w["to"]:
            out.append(f"stops[{i}].window: from is after to")
    return out


def errors(action: Any) -> list[str]:
    found = schema_errors(action)
    return found or rule_errors(action)


def batch_errors(batch: Sequence[Any]) -> list[str]:
    if not 1 <= len(batch) <= MAX_BATCH:
        return [f"a batch needs 1 to {MAX_BATCH} actions"]
    return [f"[{i}].{e}" for i, a in enumerate(batch) for e in errors(a)]


def _checked(action: dict) -> dict:
    found = errors(action)
    if found:
        raise InvalidAction(action, found)
    return action


# ---- builders ----------------------------------------------------------------------------------------

def window(start: int, end: int) -> dict:
    return {"from": start, "to": end}


def fee_step(at: int, fee_cents: int) -> dict:
    return {"at": at, "feeCents": fee_cents}


def stop(order_id: str, leg: int, kind: str, window: Optional[dict] = None,
         with_plates: Optional[bool] = None, with_charging: Optional[bool] = None) -> dict:
    s: dict = {"orderId": order_id, "leg": leg, "kind": kind}
    if window is not None:
        s["window"] = window
    if with_plates is not None:
        s["withPlates"] = with_plates
    if with_charging is not None:
        s["withCharging"] = with_charging
    return s


def quote(request_id: str, prices: Mapping[str, int]) -> dict:
    return _checked({"type": "quote", "requestId": request_id, "prices": dict(prices)})


def post(stops: Sequence[dict], experienced: bool, manual_licence: bool, schedule: Sequence[dict]) -> dict:
    return _checked({"type": "post", "stops": list(stops), "audience": {"experienced": experienced, "manualLicence": manual_licence},
                     "schedule": list(schedule)})


def offer(gig_id: str, driver_id: str, fee_cents: int) -> dict:
    return _checked({"type": "offer", "gigId": gig_id, "driverId": driver_id, "feeCents": fee_cents})


def reprice(gig_id: str, schedule: Sequence[dict]) -> dict:
    return _checked({"type": "reprice", "gigId": gig_id, "schedule": list(schedule)})


def withdraw(gig_id: str) -> dict:
    return _checked({"type": "withdraw", "gigId": gig_id})


def release(gig_id: str) -> dict:
    return _checked({"type": "release", "gigId": gig_id})
