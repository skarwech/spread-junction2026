"""The desk's books, folded from what the world told it: events (deduplicated by seq) and the results of
its own posts. Nothing here is guessed or recomputed from rules; the margin is the sum of the ledger.

The fold is mutable inside for speed (a level 8 week is tens of thousands of events); everything it hands
out (`summary`, `order_view`) is a fresh value.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

TRUST_CAP = 25  # RULES: each dealer counts up to 25 on-time orders


@dataclass
class OrderBook:
    order: dict
    won_at: int
    cancelled: bool = False
    revenue_at: Optional[int] = None
    late_refund: bool = False
    undelivered: bool = False
    closed_pos: Optional[int] = None  # position in the ledger of the line that closed the order (revenue or penalty)
    lines: list = field(default_factory=list)


class State:
    def __init__(self) -> None:
        self.requests: dict[str, dict] = {}
        self.orders: dict[str, OrderBook] = {}
        self.lost: set[str] = set()
        self.gig_cars: dict[str, list[tuple[str, int]]] = {}  # gig id -> the (order id, leg) it carries
        self.gig_status: dict[str, str] = {}
        self.ledger: list[dict] = []
        self.margin_cents = 0
        self.kinds: Counter = Counter()
        self.last_seq = -1
        self.events_seen = 0
        self.duplicates = 0
        self.now = 0

    # ---- folding --------------------------------------------------------------------------------------

    def apply_results(self, actions: list, results: list) -> None:
        for action, result in zip(actions, results):
            if action["type"] == "post" and result.get("ok") is True:
                self.gig_cars[result["id"]] = [(s["orderId"], s["leg"]) for s in action["stops"] if s["kind"] == "pickup"]
                self.gig_status[result["id"]] = "open"

    def apply_events(self, events: list) -> None:
        for e in events:
            if e["seq"] <= self.last_seq:
                self.duplicates += 1
                continue
            self.last_seq = e["seq"]
            self.events_seen += 1
            self.now = max(self.now, e["at"])
            self.kinds[e["kind"]] += 1
            handler = getattr(self, f"_on_{e['kind']}", None)
            if handler:
                handler(e)

    def _on_price_request(self, e: dict) -> None:
        self.requests[e["request"]["id"]] = e["request"]

    def _on_order_won(self, e: dict) -> None:
        self.orders[e["order"]["id"]] = OrderBook(order=e["order"], won_at=e["at"])

    def _on_order_lost(self, e: dict) -> None:
        self.lost.add(e["requestId"])

    def _on_order_changed(self, e: dict) -> None:
        book = self.orders.get(e["order"]["id"])
        if book:
            book.order = e["order"]

    def _on_order_cancelled(self, e: dict) -> None:
        book = self.orders.get(e["orderId"])
        if book:
            book.cancelled = True

    def _on_gig_booked(self, e: dict) -> None:
        self.gig_status[e["gigId"]] = "booked"

    def _on_gig_dropped(self, e: dict) -> None:
        self.gig_status[e["gigId"]] = "open"

    _on_no_show = _on_gig_dropped

    def _on_gig_started(self, e: dict) -> None:
        self.gig_status[e["gigId"]] = "working"

    def _on_gig_expired(self, e: dict) -> None:
        self.gig_status[e["gigId"]] = "expired"

    def _on_delivered(self, e: dict) -> None:
        book = self.orders.get(e["orderId"])
        if book:
            delivered = list(book.order["deliveredAt"])
            delivered[e["leg"]] = e["at"]
            book.order = {**book.order, "deliveredAt": delivered}

    def _on_ledger(self, e: dict) -> None:
        line = e["line"]
        self.ledger.append(line)
        self.margin_cents += line["cents"]
        book = self.orders.get(line["orderId"] or "")
        if book is None:
            return
        book.lines.append(line)
        if line["kind"] == "revenue":
            book.revenue_at = line["at"]
            book.closed_pos = len(self.ledger)
        elif line["kind"] == "late_refund":
            book.late_refund = True
        elif line["kind"] == "undelivered_penalty":
            book.undelivered = True
            book.closed_pos = book.closed_pos if book.closed_pos is not None else len(self.ledger)

    def set_clock(self, now: int) -> None:
        """The world's minute after each advance, so overdue orders count even between events."""
        self.now = max(self.now, now)

    # ---- views ---------------------------------------------------------------------------------------

    def won(self) -> list[OrderBook]:
        return [b for b in self.orders.values() if not b.cancelled]

    def trust(self) -> dict[str, int]:
        """Each dealer's count of on-time orders (L8): +1 per on-time order up to 25, halved on a late one.
        Counted in the order of the account lines that close each order: a revenue line with no late refund is on time."""
        counts: dict[str, int] = {}
        done = sorted((b for b in self.won() if b.closed_pos is not None), key=lambda b: b.closed_pos)
        for b in done:
            dealer = b.order["dealerId"]
            k = counts.get(dealer, 0)
            counts[dealer] = min(TRUST_CAP, k + 1) if (b.revenue_at is not None and not b.late_refund) else k // 2
        return counts

    def summary(self) -> dict:
        won = self.won()
        delivered = [b for b in won if b.revenue_at is not None]
        on_time = [b for b in delivered if not b.late_refund]
        overdue = [b for b in won if b.revenue_at is None and b.order["deadline"] < self.now]
        by_kind: Counter = Counter()
        for line in self.ledger:
            by_kind[line["kind"]] += line["cents"]
        n = len(won)
        return {
            "now": self.now,
            "marginCents": self.margin_cents,
            "revenueCents": by_kind["revenue"],
            "wonOrders": n,
            "ledgerByKind": dict(by_kind),
            "onTime": len(on_time), "delivered": len(delivered), "overdue": len(overdue),
            "undelivered": sum(b.undelivered for b in won),
            # candidate definitions of the server's shares, compared against GET /score
            "onTimeShare_onTimeOverWon": len(on_time) / n if n else 0.0,
            "onTimeShare_notLateOverWon": (n - (len(delivered) - len(on_time)) - len(overdue)) / n if n else 0.0,
            "onTimeShare_onTimeOverDue": len(on_time) / (len(delivered) + len(overdue)) if delivered or overdue else 0.0,
            "undeliveredShare": sum(b.undelivered for b in won) / n if n else 0.0,
            "events": self.events_seen, "duplicates": self.duplicates, "lastSeq": self.last_seq,
            "gigs": len(self.gig_cars), "requests": len(self.requests), "lost": len(self.lost),
        }

    def fingerprint(self) -> str:
        """A digest of the books, equal for two desks that saw the same week."""
        import hashlib
        import json
        books = {"margin": self.margin_cents, "ledger": self.ledger, "orders": sorted(self.orders), "gigs": sorted(self.gig_cars.items())}
        return hashlib.sha256(json.dumps(books, sort_keys=True).encode()).hexdigest()[:16]
