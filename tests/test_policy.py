"""Policies are pure functions of what the world said."""
import pytest

from desk.policy import Params, quote_prices

LEG = {"pickup": {"placeId": "helsinki", "window": {"from": 600, "to": 1200}}, "delivery": {"placeId": "helsinki"}}
REQUEST = {"id": "r1", "respondBy": 615, "referenceFeeCents": 5000, "note": None, "legs": [LEG],
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


def test_level_one_deadline_fee_uses_one_valid_opening_step():
    from desk.policy import PricedDesk
    p = Params(fee_mode="deadline", fee_open=0.9, fee_cap=1.85, fee_steps=6)
    desk = PricedDesk(None, 1, 700, p)
    order = _order("l1")
    desk.requests["l1"] = {**REQUEST, "id": "l1", "referenceFeeCents": 5000}
    schedule = desk.fees_for(order, 1)
    assert schedule == [{"at": 700, "feeCents": 4500}]
    from desk import actions as A
    assert A.errors({"type": "post", "stops": [{"orderId": "l1", "leg": 0, "kind": "pickup"},
                                                  {"orderId": "l1", "leg": 0, "kind": "delivery"}],
                     "audience": {"experienced": False, "manualLicence": False}, "schedule": schedule}) == []


def test_rank_all_uses_a_level_one_profile_and_keeps_cli_overrides():
    from tools.rank_all import params_for_level
    assert params_for_level(1).fee_open == 0.85
    assert params_for_level(1).max_drive_h == 4
    assert params_for_level(1).min_slack_h == 7
    assert params_for_level(8).fee_open == 0.9 and params_for_level(8).max_drive_h == 6
    assert params_for_level(1, ["fee_open=0.9"]).fee_open == 0.9


def test_params_parse_and_reject_unknown_keys():
    assert Params.parse(["price_mult=1.35", "options=all"]) == Params(price_mult=1.35, options="all")
    with pytest.raises(ValueError):
        Params.parse(["pricemult=1.3"])


def test_low_level_declines_send_no_quote_because_price_is_ignored():
    from desk.policy import PricedDesk
    for level in (1, 2, 3):
        desk = PricedDesk(None, level, 0, Params(open_order_cap=1))
        desk.quote({**REQUEST, "id": f"q{level}-1", "arrivedAt": 600, "dealerId": "D"})
        assert len(desk.outbox) == 1
        desk.outbox.clear()
        desk.quote({**REQUEST, "id": f"q{level}-2", "arrivedAt": 601, "dealerId": "D"})
        assert desk.outbox == []


def test_open_order_cap_reserves_pending_quotes_and_releases_after_delivery():
    from desk.policy import PricedDesk
    desk = PricedDesk(None, 1, 0, Params(open_order_cap=1))
    first = {**REQUEST, "id": "first", "arrivedAt": 600, "dealerId": "D"}
    desk.quote(first)
    assert desk.outbox[-1]["type"] == "quote" and desk.pending_capacity == {"first"}
    desk.outbox.clear()
    desk.quote({**REQUEST, "id": "second", "arrivedAt": 601, "dealerId": "D"})
    assert desk.outbox == []  # the first response is still pending

    desk.handle({"seq": 1, "at": 615, "kind": "order_won", "order": _order("first")})
    desk.outbox.clear()
    assert desk.pending_capacity == set() and set(desk.open_capacity) == {"first"}
    desk.quote({**REQUEST, "id": "third", "arrivedAt": 620, "dealerId": "D"})
    assert desk.outbox == []  # a won, undelivered order still consumes capacity

    desk.handle({"seq": 2, "at": 700, "kind": "delivered", "orderId": "first", "leg": 0})
    desk.outbox.clear()
    desk.quote({**REQUEST, "id": "fourth", "arrivedAt": 701, "dealerId": "D"})
    assert desk.outbox[-1]["type"] == "quote"


def test_open_order_capacity_rebuilds_through_rejoin_history():
    from desk.policy import PricedDesk
    p = Params(open_order_cap=1)
    first = {**REQUEST, "id": "first", "arrivedAt": 600, "dealerId": "D"}
    second = {**REQUEST, "id": "second", "arrivedAt": 620, "dealerId": "D"}
    won = _order("first")
    history = [
        {"seq": 1, "at": 600, "kind": "price_request", "request": first},
        {"seq": 2, "at": 615, "kind": "order_won", "order": won},
        {"seq": 3, "at": 620, "kind": "price_request", "request": second},
    ]
    desk = PricedDesk(None, 1, 620, p)
    desk.rejoin({"gigs": [], "orders": [won], "openRequests": [second]}, history)
    assert desk.open_capacity == {"first": [None]}
    assert desk.decided == {"first": True, "second": False}
    assert all(action["type"] != "quote" for action in desk.outbox)


def test_low_level_high_price_declines_remain_quotes_above_level_three():
    from desk.policy import PricedDesk
    desk = PricedDesk(None, 4, 0, Params(open_order_cap=1))
    desk.quote({**REQUEST, "id": "q4-1", "arrivedAt": 600, "dealerId": "D"})
    desk.quote({**REQUEST, "id": "q4-2", "arrivedAt": 601, "dealerId": "D"})
    assert len(desk.outbox) == 2 and desk.outbox[-1]["prices"] == {"same_day": 40004}


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


# Option choice (test final 2: 138 of 337 declines had a next_day option with enough slack).
TIGHT = {**REQUEST, "options": [{"kind": "same_day", "deadline": 1000, "listPriceCents": 10001},   # 6.4 h slack
                                {"kind": "next_day", "deadline": 2640, "listPriceCents": 8000}]}   # 33.75 h slack


def test_safe_quotes_the_slower_option_when_the_first_is_too_tight():
    assert quote_prices(TIGHT, Params(price_mult=1.5, min_slack_h=8, options="safe")) == {"next_day": 12000}
    assert quote_prices(TIGHT, Params(price_mult=1.5, min_slack_h=8, options="safe1")) == {"next_day": 12000}
    assert quote_prices(TIGHT, Params(price_mult=1.5, min_slack_h=8)) == {"same_day": 40004}  # "first" still declines


def test_safe_quotes_every_option_that_passes_and_safe1_only_the_fastest():
    assert quote_prices(TIGHT, Params(price_mult=1.5, min_slack_h=6, options="safe")) == {"same_day": 15002, "next_day": 12000}
    assert quote_prices(TIGHT, Params(price_mult=1.5, min_slack_h=6, options="safe1")) == {"same_day": 15002}


def test_safe_declines_on_the_first_option_when_no_option_passes():
    from desk.policy import declined
    p = Params(price_mult=1.5, min_slack_h=40, options="safe")
    assert declined(TIGHT, p)
    assert quote_prices(TIGHT, p) == {"same_day": 40004}


def test_long_drive_is_quoted_only_on_an_option_with_long_slack():
    far = {**TIGHT, "legs": [{"pickup": {"placeId": "helsinki", "window": {"from": 600, "to": 1200}}, "delivery": {"placeId": "tampere"}}]}
    from desk.policy import risk
    s0, drive = risk(far, far["options"][0])
    s1, _ = risk(far, far["options"][1])
    assert drive > 1.5 and s0 < 24 <= s1
    p = Params(price_mult=1.5, min_slack_h=2, max_drive_h=1.5, options="safe")
    assert quote_prices(far, p) == {"same_day": 40004}                                   # long drive: declined
    assert quote_prices(far, Params(**{**p.as_dict(), "long_slack_h": 24})) == {"next_day": 12000}


def test_a_fallback_quote_is_a_real_quote_and_rejoin_agrees():
    from desk.policy import PricedDesk
    p = Params(price_mult=1.5, min_slack_h=8, options="safe", cost_floor=1.0)
    desk = PricedDesk(None, 8, 0, p)
    req = {**TIGHT, "id": "t1", "arrivedAt": 600, "dealerId": "D", "referenceFeeCents": 5000}
    desk.quote(req)
    assert desk.outbox[-1]["prices"] == {"next_day": 12000}
    assert "t1" in desk.learning.quoted and desk.real_quote(req)


def test_options_param_rejects_unknown_modes():
    with pytest.raises(ValueError):
        Params.parse(["options=most"])
    assert Params.parse(["options=safe", "long_slack_h=24"]).long_slack_h == 24


# Overnight hold (test final 2: 45 bookings between 00:00 and 08:00 at 1.42× the typical fee, after raises no one read).
def test_night_hold_places_every_raise_between_07_and_22_and_reaches_the_cap_on_time():
    from desk.policy import deadline_schedule
    plain = deadline_schedule(1080, 10000, 2520, Params(fee_mode="deadline", fee_open=0.9, fee_cap=2.0, fee_lead_h=2, fee_steps=6))
    held = deadline_schedule(1080, 10000, 2520, Params(fee_mode="deadline", fee_open=0.9, fee_cap=2.0, fee_lead_h=2, fee_steps=6, night_hold=1))
    assert [s["at"] for s in held] == [1080, 1236, 1932, 2088, 2244, 2400]       # 18:00, 20:36, then 08:12 ... 16:00 next day
    assert [s["feeCents"] for s in held] == [s["feeCents"] for s in plain]
    assert all(not (22 * 60 <= s["at"] % 1440 or s["at"] % 1440 < 7 * 60) for s in held[1:])


def test_night_hold_never_passes_the_target_and_falls_back_when_the_whole_window_is_night():
    from desk.policy import deadline_schedule
    p = Params(fee_mode="deadline", fee_open=0.9, fee_cap=2.0, fee_lead_h=2, fee_steps=6, night_hold=1)
    # posted 21:00, last pickup 06:00 next day -> target 04:00: one active hour, the cap at 22:00 at the latest
    sched = deadline_schedule(1260, 10000, 1440 + 360, p)
    assert sched[-1]["at"] <= 1440 + 240 and sched[-1]["feeCents"] == 20000
    assert all(b["at"] > a["at"] and b["feeCents"] >= a["feeCents"] for a, b in zip(sched, sched[1:]))
    # posted 23:00, target 04:00: no active minute, so the plain schedule
    night = deadline_schedule(1380, 10000, 1440 + 360, p)
    assert night == deadline_schedule(1380, 10000, 1440 + 360, Params(**{**p.as_dict(), "night_hold": 0}))


# Bulk batches (test final 2: B0088, 15 of 21 won, €7 an order, 2 late).
def test_batch_cap_declines_real_quotes_beyond_the_cap_and_rejoin_agrees():
    from desk.policy import PricedDesk
    p = Params(price_mult=1.5, options="safe", batch_cap=2)
    def req(i, batch):
        return {**TIGHT, "id": f"b{i}", "arrivedAt": 600 + i, "respondBy": 615 + i, "dealerId": "D", "referenceFeeCents": 5000, "batchId": batch}
    live = PricedDesk(None, 8, 0, p)
    reqs = [req(0, "B1"), req(1, "B1"), req(2, None), req(3, "B1"), req(4, "B2")]
    for r in reqs:
        live.quote(r)
    prices = [a["prices"] for a in live.outbox]
    assert prices[3] == {"same_day": 40004}                          # the third real quote of B1: declined
    assert all(v == {"same_day": 15002, "next_day": 12000} for i, v in enumerate(prices) if i != 3)
    assert live.learning.quoted == {"b0", "b1", "b2", "b4"}
    live.quote(reqs[3])                                              # a re-quote keeps the first decision
    assert live.outbox[-1]["prices"] == {"same_day": 40004}
    again = PricedDesk(None, 8, 0, p)
    assert [again.real_quote(r) for r in reqs] == [True, True, True, False, True]
    assert [again.real_quote(r) for r in reqs] == [True, True, True, False, True]   # idempotent


# Long drives (step 8: 5-7 h drives earn €52 an order but 9-14% are late, 60% of them booked after lastPickupAt).
def test_long_drives_reach_their_cap_earlier_and_short_ones_do_not_change():
    from desk.policy import PricedDesk, deadline_schedule
    p = Params(fee_mode="deadline", fee_open=0.9, fee_cap=2.0, fee_lead_h=2, fee_steps=6, long_drive_h=4, long_lead_h=8, long_cap=2.5)
    desk = PricedDesk(None, 8, 600, p)
    near = {**_order("n"), "lastPickupAt": 3000}
    far = {**_order("f"), "lastPickupAt": 3000, "legs": [{**_order()["legs"][0], "delivery": {**_order()["legs"][0]["delivery"], "placeId": "rovaniemi"}}]}
    for o in (near, far):
        desk.requests[o["id"]] = {"referenceFeeCents": 10000}
    assert desk.fees_for(near, 1) == deadline_schedule(600, 10000, 3000, p)
    long_sched = desk.fees_for(far, 1)
    assert long_sched[-1] == {"at": 3000 - 8 * 60, "feeCents": 25000}
    assert long_sched[0]["feeCents"] == 9000
