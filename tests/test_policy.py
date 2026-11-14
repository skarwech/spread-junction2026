"""Policies are pure functions of what the world said."""
import pytest

from desk.policy import Params, quote_prices

LEG = {"pickup": {"placeId": "helsinki", "window": {"from": 600, "to": 1200}}, "delivery": {"placeId": "helsinki"}}
REQUEST = {"id": "r1", "respondBy": 615, "legs": [LEG],
           "options": [{"kind": "same_day", "deadline": 1200, "listPriceCents": 10001},
                       {"kind": "next_day", "deadline": 2640, "listPriceCents": 8000}]}


def test_risky_cars_are_declined_far_above_list():
    from desk.policy import risk, road_minutes
    far = {**REQUEST, "legs": [{"pickup": {"placeId": "helsinki", "window": {"from": 600, "to": 1200}}, "delivery": {"placeId": "rovaniemi"}}]}
    slack, drive = risk(far, far["options"][0])
    assert drive == road_minutes("helsinki", "rovaniemi") / 60 > 7
    assert quote_prices(far, Params(price_mult=1.5, max_drive_h=6)) == {"same_day": 40004}
    assert quote_prices(REQUEST, Params(price_mult=1.5, max_drive_h=6, min_slack_h=4)) == {"same_day": 15002}  # 9.75 h slack, 0 drive
    assert quote_prices(REQUEST, Params(price_mult=1.5, min_slack_h=10)) == {"same_day": 40004}


def test_starter_equivalent_price_is_the_list_price_of_the_first_option():
    assert quote_prices(REQUEST, Params()) == {"same_day": 10001}


def test_multiplier_rounds_half_up_to_whole_cents():
    assert quote_prices(REQUEST, Params(price_mult=1.5)) == {"same_day": 15002}  # 15001.5 -> 15002


def test_all_options_are_quoted_when_asked():
    assert quote_prices(REQUEST, Params(price_mult=1.25, options="all")) == {"same_day": 12501, "next_day": 10000}


def test_deadline_schedule_rises_to_the_cap_before_last_pickup():
    from desk import actions as A
    from desk.policy import deadline_schedule
    p = Params(fee_mode="deadline", fee_open=1.0, fee_cap=2.0, fee_lead_h=2.0, fee_steps=5)
    s = deadline_schedule(600, 5000, 600 + 10 * 60, p)
    assert s[0] == {"at": 600, "feeCents": 5000}
    assert s[-1] == {"at": 600 + 8 * 60, "feeCents": 10000}
    assert len(s) == 5 and A.rule_errors({"type": "reprice", "gigId": "g", "schedule": s}) == []


def test_deadline_schedule_goes_straight_to_the_cap_when_late_and_never_falls():
    from desk import actions as A
    from desk.policy import deadline_schedule
    p = Params(fee_mode="deadline", fee_open=1.2, fee_cap=1.0, fee_lead_h=2.0, fee_steps=6)  # cap below open: open wins
    assert deadline_schedule(900, 3333, 950, p) == [{"at": 900, "feeCents": 4000}]
    tight = deadline_schedule(900, 3333, 900 + 2 * 60 + 3, Params(fee_mode="deadline", fee_steps=6))
    assert A.errors({"type": "reprice", "gigId": "g", "schedule": tight}) == []
    assert [s["at"] for s in tight] == sorted(set(s["at"] for s in tight))


def test_params_parse_and_reject_unknown_keys():
    assert Params.parse(["price_mult=1.35", "options=all"]) == Params(price_mult=1.35, options="all")
    with pytest.raises(ValueError):
        Params.parse(["pricemult=1.3"])


def _req(rid, dealer, at=100):
    return {"seq": 0, "at": at, "kind": "price_request", "request": {"id": rid, "dealerId": dealer}}


def _line(kind, oid, at):
    return {"seq": 0, "at": at, "kind": "ledger", "line": {"at": at, "kind": kind, "cents": 1, "orderId": oid, "gigId": None, "detail": ""}}


def test_trust_counts_on_time_orders_and_halves_on_a_late_one_in_the_same_minute():
    from desk.policy import Learning
    L = Learning(Params(trust_markup=0.01))
    for rid in ("A", "B", "C"):
        L.see(_req(rid, "D1"))
    L.see(_line("revenue", "A", 200))
    L.see(_line("revenue", "C", 300))
    L.see({"seq": 0, "at": 301, "kind": "forecast"})
    assert L.trust == {"D1": 2}
    L.see(_line("revenue", "B", 400))
    L.see(_line("late_refund", "B", 400))  # same minute, after its revenue line
    L.see({"seq": 0, "at": 401, "kind": "forecast"})
    assert L.trust == {"D1": 1}
    assert abs(L.multiplier("D1", 401) - 1.0 * 1.01) < 1e-12


def test_ladder_steps_up_on_a_high_win_rate_then_down_and_brake_takes_the_top_rung():
    from desk.policy import Learning
    L = Learning(Params(price_mult=1.5, ladder_step=0.15, ladder_up=0.5, ladder_down=0.2, ladder_n=4, brake_dc=2))
    for i, won in enumerate([1, 1, 0, 1]):
        L.quoted.add(f"r{i}")
        L.see({"seq": 0, "at": 10, "kind": "order_won", "order": {"id": f"r{i}"}} if won else {"seq": 0, "at": 10, "kind": "order_lost", "requestId": f"r{i}"})
    assert L.rung == 1 and L.window == []
    for i in range(4, 8):
        L.quoted.add(f"r{i}")
        L.see({"seq": 0, "at": 20, "kind": "order_lost", "requestId": f"r{i}"})
    assert L.rung == 0
    L.see({"seq": 0, "at": 100, "kind": "deadline_close", "orderId": "x", "lastPickupAt": 0})
    L.see({"seq": 0, "at": 200, "kind": "deadline_close", "orderId": "y", "lastPickupAt": 0})
    assert abs(L.multiplier("D", 300) - 1.8) < 1e-12 and abs(L.multiplier("D", 1700) - 1.5) < 1e-12


def test_declined_quotes_do_not_move_the_ladder():
    from desk.policy import Learning
    L = Learning(Params(ladder_up=0.5, ladder_n=1))
    L.see({"seq": 0, "at": 10, "kind": "order_won", "order": {"id": "never-quoted"}})
    assert L.window == [] and L.rung == 0


def _outcome(rid, won, at):
    return {"seq": 0, "at": at, "kind": "order_won", "order": {"id": rid}} if won else {"seq": 0, "at": at, "kind": "order_lost", "requestId": rid}


def test_adaptive_price_walks_down_while_losing_and_never_moves_without_new_outcomes():
    from desk.policy import Learning
    L = Learning(Params(price_mult=1.5, target_win=0.3, adapt_k=0.6, adapt_alpha=0.1, adapt_every=30, adapt_min_new=5, adapt_max_step=0.04, m_min=1.0))
    at = 600
    for i in range(50):  # every quote lost
        L.quoted.add(f"r{i}")
        at += 7
        L.see(_outcome(f"r{i}", False, at))
    assert 1.0 <= L.m < 1.5 and len(L.history) >= 5
    assert all(b[1] <= a[1] for a, b in zip(L.history, L.history[1:]))   # only down
    steps = [b[1] / a[1] for a, b in zip(L.history, L.history[1:])]
    assert min(steps) >= __import__("math").exp(-0.04) - 1e-4          # at most 4% per update (history is rounded to 4 decimals)
    m_night = L.m
    for k in range(40):  # a night: events but no outcomes
        L.see({"seq": 0, "at": at + 30 * (k + 1), "kind": "forecast"})
    assert L.m == m_night


def test_intake_cap_pushes_the_price_up_even_when_winning_little():
    from desk.policy import Learning
    L = Learning(Params(price_mult=1.3, target_win=0.9, adapt_every=1, adapt_min_new=1, intake_cap=3))
    for i in range(6):
        L.quoted.add(f"r{i}")
        L.see(_outcome(f"r{i}", True, 100 + i * 2))
    assert L.m > 1.3


def test_no_quote_before_start_minute_and_cost_floor(monkeypatch):
    from desk.policy import PricedDesk
    desk = PricedDesk(None, 8, 0, Params(price_mult=1.0, start_minute=4320, cost_floor=1.2))
    early = {**REQUEST, "id": "early", "arrivedAt": 600, "dealerId": "D", "referenceFeeCents": 9000}
    desk.quote(early)
    assert desk.outbox == []
    late = {**REQUEST, "id": "late", "arrivedAt": 4400, "respondBy": 4415, "dealerId": "D", "referenceFeeCents": 9000,
            "options": [{"kind": "same_day", "deadline": 4400 + 600, "listPriceCents": 10001}],
            "legs": [{"pickup": {"placeId": "helsinki", "window": {"from": 4400, "to": 5000}}, "delivery": {"placeId": "helsinki"}}]}
    desk.quote(late)
    assert desk.outbox[-1]["prices"] == {"same_day": 10800}  # max(1.0 × 10001, 1.2 × 9000)


def test_rejoin_rebuilds_the_adaptive_price_exactly():
    from desk.policy import PricedDesk
    p = Params(price_mult=1.5, target_win=0.3, adapt_every=30, adapt_min_new=3)
    def req(i, at):
        return {"seq": 0, "at": at, "kind": "price_request", "request": {**REQUEST, "id": f"q{i}", "arrivedAt": at, "respondBy": at + 15, "dealerId": "D", "referenceFeeCents": 5000,
                "options": [{"kind": "next_day", "deadline": at + 2000, "listPriceCents": 8000}],
                "legs": [{"pickup": {"placeId": "helsinki", "window": {"from": at, "to": at + 600}}, "delivery": {"placeId": "helsinki"}}]}}
    history = []
    for i in range(30):
        history += [req(i, 600 + 20 * i), _outcome(f"q{i}", i % 5 == 0, 615 + 20 * i)]
    live = PricedDesk(None, 8, 0, p)
    for e in history:
        live.learning.see(e) if e["kind"] != "price_request" else (live.quote(e["request"]), live.learning.see(e))
    again = PricedDesk(None, 8, 0, p)
    again.learning.quoted = set()
    for e in history:
        if e["kind"] == "price_request" and again.real_quote(e["request"]):
            again.learning.quoted.add(e["request"]["id"])
        again.learning.see(e)
    assert again.learning.m == live.learning.m and again.learning.history == live.learning.history and len(live.learning.history) > 2


def _order(oid="o1"):
    leg = {"car": {"premium": False, "electric": False, "chargePercent": None},
           "pickup": {"placeId": "helsinki", "window": {"from": 600, "to": 1200}, "privateAddress": False, "hours": None},
           "delivery": {"placeId": "espoo", "window": {"from": 600, "to": 1200}, "privateAddress": False, "hours": None}}
    return {"id": oid, "dealerId": "D", "option": "next_day", "priceCents": 10000, "deadline": 2640, "legs": [leg],
            "status": "waiting", "deliveredAt": [None], "lastPickupAt": 2000}


def test_a_failed_visit_after_a_rejoin_post_is_not_posted_twice():
    from desk.policy import PricedDesk
    desk = PricedDesk(None, 8, 700, Params())
    desk.orders["o1"] = _order()
    desk.requests["o1"] = {**REQUEST, "id": "o1", "referenceFeeCents": 5000, "note": None}
    desk.outbox.append({"type": "post", "stops": [{"orderId": "o1", "leg": 0, "kind": "pickup"}, {"orderId": "o1", "leg": 0, "kind": "delivery"}],
                        "audience": {"experienced": False, "manualLicence": False}, "schedule": [{"at": 700, "feeCents": 5000}]})
    desk.retry("o1", 0, "not_ready")
    assert sum(a["type"] == "post" for a in desk.outbox) == 1


def test_a_refused_post_with_an_ended_window_is_posted_again_without_its_windows():
    from desk.policy import PricedDesk
    desk = PricedDesk(None, 8, 700, Params())
    desk.orders["o1"] = _order()
    post = {"type": "post", "stops": [{"orderId": "o1", "leg": 0, "kind": "pickup", "window": {"from": 600, "to": 650}},
                                      {"orderId": "o1", "leg": 0, "kind": "delivery"}],
            "audience": {"experienced": False, "manualLicence": False}, "schedule": [{"at": 700, "feeCents": 5000}]}
    desk.read_results([post], [{"ok": False, "reason": "a stop window has ended"}])
    assert len(desk.outbox) == 1 and all("window" not in s for s in desk.outbox[0]["stops"])
    desk.outbox.clear()
    desk.read_results([{**post, "stops": [{k: v for k, v in s.items() if k != "window"} for s in post["stops"]]}],
                      [{"ok": False, "reason": "refused again"}])
    assert desk.outbox == []  # no windows left to drop: no loop
