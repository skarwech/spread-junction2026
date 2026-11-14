"""Policies: what the desk decides. Each is the kit starter's logistics (posting, retries, note windows,
trade-in splits) with one idea changed, so the effect of each idea can be measured on its own.

- `starter`: the kit's Desk, unchanged.
- `priced`:  quotes `price_mult` × list price instead of the list price (idea 1: win fewer cars, at a margin).

Every decision is a pure function of what the world said, so a desk replays exactly after a restart.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from typing import Any

from spread.starter import Desk
from spread.types import PriceRequest

from desk import actions as A


@dataclass(frozen=True)
class Params:
    price_mult: float = 1.0      # quote = round(list price × price_mult)
    options: str = "first"       # "first": quote the dealer's first option only (as the starter); "all": every offered option
    fee_mode: str = "starter"    # "starter": +10%/h up to 1.5× typical; "deadline": reach fee_cap before lastPickupAt
    fee_open: float = 1.0        # opening fee, × the typical fee
    fee_cap: float = 2.0         # fee reached fee_lead_h hours before lastPickupAt
    fee_lead_h: float = 2.0
    fee_steps: float = 6
    min_slack_h: float = -999.0  # decline when deadline − ready time − driving time is shorter than this
    max_drive_h: float = 999.0   # decline when the car's driving time is longer than this
    decline_mult: float = 4.0    # a decline is a quote this far above list (RULES.md:47: losing quotes cost nothing)
    trust_markup: float = 0.0    # × (1 + trust_markup × the dealer's on-time count, ≤ 25) (RULES.md:163-165)
    ladder_step: float = 0.15    # price rungs: price_mult + {0, 1, 2} × ladder_step
    ladder_up: float = 999.0     # one rung up when the win rate of the last ladder_n answered quotes is ≥ this
    ladder_down: float = -1.0    # one rung down when it is < this
    ladder_n: float = 40
    brake_dc: float = 999.0      # top rung while this many deadline warnings fell in the last 24 h
    target_win: float = -1.0     # adaptive price: steer the multiplier so this share of real quotes wins (off when < 0)
    adapt_k: float = 0.6         # log-step per unit of (smoothed win rate − target)
    adapt_alpha: float = 0.1     # smoothing weight of each new outcome
    adapt_every: float = 30      # world minutes between price updates ...
    adapt_min_new: float = 5     # ... and only after this many new outcomes (no drift overnight)
    adapt_max_step: float = 0.04  # at most ±4% per update (a bulk order cannot swing it at once)
    m_min: float = 1.0
    m_max: float = 1.9
    intake_cap: float = 999.0    # orders won in the last 24 h at which the price goes up instead (a leading load signal)
    cost_floor: float = 0.0      # every real quote ≥ the request's typical fee × this
    start_minute: float = 0      # no quote before this minute (emulates a final that starts on Thursday)

    @classmethod
    def parse(cls, pairs: list[str]) -> "Params":
        types = {f.name: f.type for f in fields(cls)}
        values: dict[str, Any] = {}
        for pair in pairs:
            key, _, raw = pair.partition("=")
            if key not in types:
                raise ValueError(f"unknown parameter {key!r}; known: {', '.join(types)}")
            values[key] = float(raw) if types[key] in ("float", float) else raw
        if values.get("fee_mode", "starter") not in ("starter", "deadline") or values.get("options", "first") not in ("first", "all"):
            raise ValueError("fee_mode is starter|deadline, options is first|all")
        return cls(**values)

    def as_dict(self) -> dict:
        return asdict(self)


ROAD_MINUTES: dict[tuple[str, str], int] = {}


def road_minutes(a: str, b: str) -> int:
    """Road minutes between two places, from the public map (data/map.json, GET /v1/map)."""
    if not ROAD_MINUTES:
        import json
        from pathlib import Path
        roads = json.loads((Path(__file__).resolve().parents[1] / "data" / "map.json").read_text(encoding="utf-8"))["roads"]
        ROAD_MINUTES.update({(r["from"], r["to"]): r["minutes"] for r in roads})
    return 0 if a == b else ROAD_MINUTES[(a, b)]


def risk(request: PriceRequest, option: dict) -> tuple[float, float]:
    """(slack hours, driving hours) of an option, known at quote time: slack = deadline − (the later of the
    cars' ready time and the answer) − the driving time of all legs."""
    drive = sum(road_minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in request["legs"])
    ready = max(max(l["pickup"]["window"]["from"] for l in request["legs"]), request["respondBy"])
    return (option["deadline"] - ready - drive) / 60, drive / 60


def declined(request: PriceRequest, params: Params) -> bool:
    options = request["options"] if params.options == "all" else request["options"][:1]
    slack, drive = risk(request, options[0])
    return slack < params.min_slack_h or drive > params.max_drive_h


def quote_prices(request: PriceRequest, params: Params, mult: float | None = None) -> dict[str, int]:
    """The quote: `mult` × list (default price_mult) on the quoted options, or a decline far above list."""
    options = request["options"] if params.options == "all" else request["options"][:1]
    if declined(request, params):
        first = request["options"][0]
        return {first["kind"]: max(1, int(first["listPriceCents"] * params.decline_mult + 0.5))}
    m = params.price_mult if mult is None else mult
    return {o["kind"]: max(1, int(o["listPriceCents"] * m + 0.5)) for o in options}


class Learning:
    """What the desk learns from its own week, from events only (so it replays exactly):
    - each dealer's on-time count, as RULES.md:163-165 count trust: +1 per on-time order up to 25, halved on a
      late one; an order closes at its revenue line, and its late refund (if any) comes in the same minute;
    - the win rate of its recent non-declined quotes, which moves a price ladder;
    - the deadline warnings of the last 24 h, which pull the brake."""

    def __init__(self, params: Params):
        self.p = params
        self.trust: dict[str, int] = {}
        self.pending: list[tuple[int, str, str]] = []  # (minute, order id, dealer) closed by a revenue line
        self.late: set[str] = set()
        self.quoted: set[str] = set()                  # requests quoted at a real price (not declined)
        self.window: list[int] = []
        self.rung = 0
        self.warnings: list[int] = []
        self.dealer_of: dict[str, str] = {}
        self.m = params.price_mult                      # the adaptive multiplier (target_win ≥ 0)
        self.smoothed = params.target_win               # smoothed win rate of real quotes, starts neutral
        self.new_outcomes = 0
        self.last_update = -10**9
        self.wins_at: list[int] = []                    # minutes of our order_won events
        self.history: list[tuple[int, float]] = []      # (minute, multiplier) after each update, for the evidence page

    def _close_pending(self, now: int) -> None:
        keep = []
        for minute, oid, dealer in self.pending:
            if minute < now:
                k = self.trust.get(dealer, 0)
                self.trust[dealer] = k // 2 if oid in self.late else min(25, k + 1)
            else:
                keep.append((minute, oid, dealer))
        self.pending = keep

    def see(self, event: dict) -> None:
        self._close_pending(event["at"])
        kind = event["kind"]
        if kind == "price_request":
            self.dealer_of[event["request"]["id"]] = event["request"]["dealerId"]
        elif kind in ("order_won", "order_lost"):
            rid = event["order"]["id"] if kind == "order_won" else event["requestId"]
            if kind == "order_won":
                self.wins_at.append(event["at"])
            if rid in self.quoted:
                won = 1 if kind == "order_won" else 0
                self.window.append(won)
                self._step()
                self.smoothed += self.p.adapt_alpha * (won - self.smoothed)
                self.new_outcomes += 1
        elif kind == "deadline_close":
            self.warnings.append(event["at"])
        elif kind == "ledger":
            line = event["line"]
            oid = line["orderId"]
            if line["kind"] == "revenue" and oid in self.dealer_of:
                self.pending.append((line["at"], oid, self.dealer_of[oid]))
            elif line["kind"] in ("late_refund", "undelivered_penalty") and oid:
                self.late.add(oid)
                if line["kind"] == "undelivered_penalty" and oid in self.dealer_of and all(o != oid for _, o, _ in self.pending):
                    self.pending.append((line["at"], oid, self.dealer_of[oid]))
        self._adapt(event["at"])

    def _adapt(self, now: int) -> None:
        """The adaptive price: every adapt_every minutes with enough new outcomes, move the multiplier toward
        the target win rate (or up while the last 24 h's intake is at the cap), by at most adapt_max_step."""
        p = self.p
        if p.target_win < 0 or now - self.last_update < p.adapt_every or self.new_outcomes < p.adapt_min_new:
            return
        intake = sum(1 for t in self.wins_at if t > now - 1440)
        step = p.adapt_max_step if intake >= p.intake_cap else p.adapt_k * (self.smoothed - p.target_win)
        step = max(-p.adapt_max_step, min(p.adapt_max_step, step))
        self.m = max(p.m_min, min(p.m_max, self.m * math.exp(step)))
        self.last_update, self.new_outcomes = now, 0
        self.history.append((now, round(self.m, 4)))

    def _step(self) -> None:
        n = int(self.p.ladder_n)
        if len(self.window) < n:
            return
        rate = sum(self.window[-n:]) / n
        if rate >= self.p.ladder_up and self.rung < 2:
            self.rung, self.window = self.rung + 1, []
        elif rate < self.p.ladder_down and self.rung > 0:
            self.rung, self.window = self.rung - 1, []

    def multiplier(self, dealer: str, now: int) -> float:
        braking = sum(1 for t in self.warnings if t > now - 1440) >= self.p.brake_dc
        if self.p.target_win >= 0:
            base = max(self.m, self.p.price_mult + 2 * self.p.ladder_step) if braking else self.m
        else:
            base = self.p.price_mult + (2 if braking else self.rung) * self.p.ladder_step
        return base * (1 + self.p.trust_markup * self.trust.get(dealer, 0))


def deadline_schedule(now: int, base: float, last_pickup: int, params: Params) -> list[dict]:
    """Opens at fee_open × base and rises in even steps to fee_cap × base by lastPickupAt − fee_lead_h, so a car
    that no driver has taken is at its highest fee while a driver can still collect it in time. When that moment
    has passed already, the cap applies at once. Times strictly rise, fees never fall, whole cents."""
    opening, cap = base * params.fee_open, base * max(params.fee_open, params.fee_cap)
    target = last_pickup - int(params.fee_lead_h * 60)
    steps = max(1, int(params.fee_steps))
    if target <= now or steps == 1:
        return [A.fee_step(now, max(1, int(cap + 0.5)))]
    schedule: list[dict] = []
    for k in range(steps):
        at = now + (target - now) * k // (steps - 1)
        fee = max(1, int(opening + (cap - opening) * k / (steps - 1) + 0.5))
        if schedule and at <= schedule[-1]["at"]:
            schedule[-1] = A.fee_step(schedule[-1]["at"], max(fee, schedule[-1]["feeCents"]))
        else:
            schedule.append(A.fee_step(at, max(fee, schedule[-1]["feeCents"] if schedule else fee)))
    return schedule


class PricedDesk(Desk):
    """The starter with our price and, optionally, our fee schedule."""

    def __init__(self, world: Any, level: int, now: int, params: Params):
        super().__init__(world, level, now)
        self.params = params
        self.learning = Learning(params)

    def handle(self, event: dict) -> None:
        self.learning.see(event)
        super().handle(event)

    def rejoin(self, snapshot: dict, history: list) -> None:
        """After a restart: relearn from the whole history first, so the re-quotes of open requests use it. Which
        requests were quoted at a real price follows from the request alone (`real_quote`), so it is rebuilt too."""
        for event in history:
            if event["kind"] == "price_request" and self.real_quote(event["request"]):
                self.learning.quoted.add(event["request"]["id"])
            self.learning.see(event)
        for request in snapshot["openRequests"]:
            self.learning.dealer_of[request["id"]] = request["dealerId"]
        super().rejoin(snapshot, history)

    def retry(self, order_id: str, leg: int, reason: str) -> None:
        """The kit's retry, but never a second post for a leg already waiting in the outbox: after a rejoin, a car
        whose visit failed while the desk was down is posted once by the rejoin (live-desk review, 14 Nov)."""
        if any(a["type"] == "post" and any(s["orderId"] == order_id and s["leg"] == leg for s in a["stops"]) for a in self.outbox):
            return
        super().retry(order_id, leg, reason)

    def read_results(self, actions: list, results: list) -> None:
        """The kit's, plus: a post the world refused because one of its own stop windows had already ended (the
        desk's clock can lag in a backlog) goes again once without those windows, so the order's window applies."""
        super().read_results(actions, results)
        for action, result in zip(actions, results):
            if action["type"] != "post" or result.get("ok") or not any("window" in s for s in action["stops"]):
                continue
            order = self.orders.get(action["stops"][0]["orderId"])
            if order is None:
                continue
            self.outbox.append({**action, "stops": [{k: v for k, v in s.items() if k != "window"} for s in action["stops"]]})

    def real_quote(self, request: PriceRequest) -> bool:
        return request["arrivedAt"] >= self.params.start_minute and not declined(request, self.params)

    def quote(self, request: PriceRequest) -> None:
        self.requests[request["id"]] = request
        self.learning.dealer_of[request["id"]] = request["dealerId"]
        if request["arrivedAt"] < self.params.start_minute:
            return  # emulates a final that starts later: requests before it go unquoted, as in the test final
        mult = self.learning.multiplier(request["dealerId"], max(self.now, request["arrivedAt"]))
        prices = quote_prices(request, self.params, mult)
        if self.real_quote(request):
            self.learning.quoted.add(request["id"])
            floor = int(request["referenceFeeCents"] * self.params.cost_floor + 0.999)
            prices = {kind: max(cents, floor) for kind, cents in prices.items()}
        self.outbox.append(A.quote(request["id"], prices))

    def fees_for(self, order: dict, cars: int) -> list:
        if self.params.fee_mode != "deadline" or order["id"] in self.urgent:
            return super().fees_for(order, cars)  # after the deadline warning: the starter's steep fees
        base = self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
        return deadline_schedule(self.now, base, order["lastPickupAt"], self.params)


def make_desk(policy: str, world: Any, level: int, now: int, params: Params) -> Desk:
    if policy == "starter":
        return Desk(world, level, now)
    if policy == "priced":
        return PricedDesk(world, level, now, params)
    raise ValueError(f"unknown policy {policy!r}")
