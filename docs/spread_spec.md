# Spread: living spec

**Version:** v1, 13 Nov 2026 (Junction 2026, all times Helsinki)
**Sources:** RULES.md (authoritative), API.md, HANDBOOK.md, the "how it works" and "judging" pages, earlier analysis.
**Legend:** **[verify]** = not yet confirmed from the docs or the kit code. **[hyp]** = hypothesis to test by experiment.
**Security:** never commit the team key. Keep `SPREAD_URL` and `SPREAD_KEY` in an untracked `.env`.

**Goal.** Be *ranked* in the final (at least 90% of won orders on time), finish in the *top 10 by margin*, then win the jury on elegance, clarity, creativity and robustness. After the top 10, margin no longer counts.

---

## 0. Status board (edit as you go)

- [x] G0: starter reproduced to the cent on `spread-1` (L8 −72,612.51 · L7 −50,442.49 · L6 −1,172.51). Fri 21:3x, all 10 L8 lines on every field; evidence `evidence/g0/`, page `proof/g0.html`
- [x] Public board JSON read (House best and House starter, per world): `data/board/level{6,7,8}.json`, round 3
- [x] `spread/types.py` and starter code read, action builders written: `desk/actions.py`, never looser than openapi.json on 5,000 fuzzed actions
- [ ] About 40 real notes collected, grammar parser tests written
- [x] Engine core: event store, state, `--resume`, restart-invariance test: `desk/journal.py`, `worldio.py`, `state.py`, `runner.py`; 18 SIGKILLs over 6 L8 runs, all identical to the control (`evidence/restart/`, `proof/core.html`). Server mid-week `onTimeShare` = on-time ÷ (delivered + overdue)
- [ ] Constraint layer: 0 fines and 0 failed visits at L5–6
- [ ] Fee engine v1: L6 at 90% on time or better
- [ ] Pricer v1 and μ governor: L7/L8 ranked on 10/10 dev seeds
- [ ] Ablations done: pooling, relay offers, soft windows, selectivity
- [ ] Preliminary submission (Fri 23:59)
- [x] Test final 1 passed (Sat 14:00): desk answered 417/417 requests in time on the real clock, 1 unplanned restart recovered in 3.3 s, ranked 100% on time; but only 12 orders, +€330.50 (49 of 55 ranked teams earned more: top won 135-167 orders, €3.1-4.0k). Price must adapt to the world. `proof/live.html`, `evidence/rehearsal/testfinal1.json`
- [x] Test final 2 ran (Sat 20:00): desk quoted 1030/1030 requests in time (median 0.026 s), 1 dropped connection recovered in 3.6 s; ranked, 97.5% on time, 279 orders, +€7,796.59; rank 62 of 75 ranked teams (234 played; top 10 from €16,623, 356-500 orders). Gap: 337 requests declined (166 short slack on the first option, 138 of them fine on next_day; 171 drives over 5 h) and fees €65 an order (median = the 0.9× opening fee). `evidence/rehearsal/tf2_*.json`
- [x] Step 8 margin push (Sat 20:45-22:00): quote every option that passes the risk test, drives ≤ 6 h, slack ≥ 8 h, no fee raises 22:00-07:00. 16 fresh L8 weeks: 16/16 ranked, +16.3% margin (€143,934 vs €123,805), worst week 93.2% vs 90.6%. Live rehearsal of the exact command (2×, SIGKILL): 1015/1015 live requests quoted, 96.9% on time, +€16,428. `proof/push8.html`, `evidence/sweeps/push3-7, holdout8-9`
- [x] Final-day fee-cap retune (Sun): `fee_cap=1.85`, validated on 16 fresh paired L8 weeks. 16/16 ranked; margin €148,177 vs €140,585 at 2.0× (+€475/week); worst on-time 92.41% vs 93.01%; 14/16 paired weeks higher; canary clean. Lower 1.75× cap missed the 92% buffer (91.97%).
- [x] Post-final risk retune: `min_slack_h=7`, independently validated on 16 fresh paired L8 weeks. 16/16 ranked vs 15/16 at 8 h; worst on-time 92.62% vs 88.93%; +€230.81/week; canary clean. Adopted for future runs. `max_drive_h=6.5` rejected after a holdout rank failure. The completed final used the 8 h setting.
- [x] Code freeze (Sun, after fee-cap retune and 100 passing regression tests)
- [x] Final ran: 36th, ranked, €5,912.57, 94.42% on time, 251 won orders, 0 undelivered. Reveal: 824/824 seen requests quoted; 212/1,036 requests had passed before attachment at world minute 1205. p99 quote latency 0.096 s; no stream errors, gaps, or drops. `evidence/final.json`, `runs/f88a11d932a63ddb3f413/live_summary.json`, public `/v1/leaderboard`
- [x] Season 10 board evaluation: 40 ranked runs, five weeks per level L1–L8, using the current L8 policy. L2–L8 ranked 5/5 each; L1 ranked 0/5 (1.48% aggregate on time, −€730,582.88). L8 placed 52nd at €50,220 vs Juhus at €102,581.93 on the same five weeks. `tools/rank_all.py`, `evidence/ranking_current/season10.json`
- [ ] Final submission (Sun 10:00)

---

## 1. Rules digest (RULES.md wins over everything else)

### 1.1 Scoring and ranking
- **Score** = sum of the account: prices in; driver fees, refunds, penalties, fines out. Amounts are whole cents, times are whole world minutes.
- **Ranked** = at least 1 won order and at least 90% of won orders on time. *On time* = every leg delivered by its deadline. Cancelled orders do not count. A car undelivered at the end counts as late.
- **Final:** one secret level-8 week. The published plan listed Sun 15 Nov 08:00, but the public feed recorded the actual start at `2026-11-14T23:00:00Z` (01:00 Helsinki); the final ended around 01:34. The 10 ranked teams with the highest margin present to the jury. Same margin to the cent shares a rank. For the actual result and timing, see `evidence/final_leaderboard.json`.
- **Ranking rounds** (practice): 5 secret worlds per level, identical for all teams. A team is ranked in a round when it has played all five and each run meets the 90% minimum; its margin is the sum. Rounds do not count for the final. `house-…` teams (House starter, House best) play every round.

### 1.2 The week and requests
- About 1,000 requests, Mon 08:00 to Fri 18:00 (almost all 09:00–18:00). 30 towns, Helsinki to Rovaniemi. Deadlines are 20:00 on business days. The next Monday is the last business day; the world ends Wed 22:00. Saturday: short site hours, some closed. Sunday: all closed.
- **Request:** dealer; 1–2 legs; private-address flags and windows; options with deadline and list price; `referenceFeeCents` (typical fee); optional note; `respondBy` = arrival + 15 min.
- **Options:** `same_day` (offered only if the request arrives by 15:00 and the car, collected when ready, can arrive 2 h before the deadline), `next_day`, `within_3_days` (3rd business day after the ready day, not after the last Monday).
- A **trade-in** (new car out, old car back) has one price and **one option only**. A private delivery also has one option; its deadline is the end of the booked hour + 30 min. A private seller's slot starts at least 1.5 h after `respondBy`.
- Order windows at dealer sites end at the chosen option's deadline. Snow moves deadlines and windows. A car ready a day or more later than stated moves the deadline by the same days.

### 1.3 Quotes
- One price per option you offer (at least one). A new quote **replaces** the earlier one. You cannot withdraw a quote. A quote at or after `respondBy` is refused.
- To decline, quote far above the list price (use at least 4× list **[verify no cap]**). A losing quote costs nothing. An unquoted request costs a little goodwill. Always quote.
- The dealer decides at `respondBy` on your last quote, comparing with the competitor's price and with each option's value to it.

### 1.4 Gigs
- **Stops** in a fixed order. Each stop may carry its own window: it may not start before the order's window; at a private pickup it must end inside the slot; at other stops it may end after the order's window (a late car can still go).
- A stop **without** its own window uses the order's window (cut to site hours). When that window has ended, or no driver can still reach every stop inside it, the stop **runs to the end of the world**. A late car can always be posted without windows. A private seller's slot never extends.
- **Pickup flags:** `withPlates` (+30 min), `withCharging` (+40 min).
- **Audience:** everyone, or experienced only (rating ≥ 4.8 and ≥ 50 completed gigs); plus a "manual licence required" flag.
- **Fee schedule:** 1–48 steps of (time, fee), time-ordered, fees never fall inside a schedule. The app shows the latest started step; before the first step starts it shows the first step's fee. `reprice` replaces the whole schedule: steps may start now, earlier or later, and fees may be **below** the current app fee. `withdraw` only if unbooked. A new fee sends no notification.
- **Multi-car gig:** at most 12 h of planned driving, including the drives between cars (plates and charging do not count).
- **Trade-in:** one gig, old-car pickup right after the new-car delivery. Its slot does not end the gig, and the gig stays bookable after the customer's hour. Split into two gigs only above 12 h. The old car posted alone must be collected inside the slot, else the dealer rebooks the next business day (`order_changed`).
- The world refuses a gig whose stop window has already ended. An open gig leaves the app the minute after the first stop window ends (`gig_expired`).
- A driver books only if they can reach every stop inside its window (road minutes plus plates and charging minutes). A 7 h drive with a delivery window ending 20:00 gets no driver after 13:00.
- `driver_late` (first pickup is a dealer site open on arrival): the driver still comes; release is free until they leave. `no_show` (any other pickup): the gig reopens.
- `deadline_close` fires 3 h before `lastPickupAt` if the order has no driver. **`lastPickupAt` comes from the server** (snapshot, `order_won`, `order_changed`); do not recompute it.
- **Release** until `gig_started`: fee of 25% (pickup more than 24 h away), 50% (less), 100% (less than 2 h). Free after `driver_late`.

### 1.5 Drivers and offers
- Drivers have homes and days (whether they work is hidden). A gig costs drive time, the trip to the pickup (ticket bought ahead), the trip home (ticket on the day, dearer), and extras (evening, weekend, private address, trade-in, charging, plates, dislikes). Far morning pickups may need a night away. A driver books a later day only if they know they will work it.
- **Notifications:** pickup within 30 km (straight line) of the driver's home; **once per order** (again only when a gig returns after a drop or no-show); none read 23:00–07:00; a raise never notifies.
- **Learning (from L2):** each driver learns, from orders they viewed and could do, the booked fee ÷ first viewed fee and the minutes from first view to booking. A gig keeps its age across reposts. A long-aged gig makes drivers wait for a raise; close to pickup they wait less.
- **Drops:** likelier the longer a booking is held and when the fee only just pays; rare at night; reliable drivers rarely drop for a better gig; a driver who dropped books again only for a higher fee.
- **Direct offers:** one gig, one driver, 10 min, a fee you choose. At most **3 per driver per day** and **3 open per gig**. A yes books at once; a no or an unread offer shows only after the 10 min. None read 23:00–07:00; drivers not working that day read few.
- You see a driver's position only while they work one of your gigs. `GET /drivers`: home town, rating, licence, completed gigs, past drops (up to 5 s stale).

### 1.6 Notes grammar (deterministic part)
- Days count from the day the request arrives. A bare time = that day; "tänään/idag/today" = that day; "huomenna/i morgon/tomorrow/tmrw/imorgon" = next day; "ylihuomenna/i övermorgon/day after tomorrow" = the day after.
- A weekday name (also short or spoken: "to.", "Thurs") = that weekday **2 to 6 days** after arrival. A note never names the arrival day or next day by weekday.
- Digits = 24-hour clock unless am/pm follows. An hour in words (Finnish, Swedish, English) is a working hour 9–17: "two" = 14:00; "half three" = 14:30.
- Corrections count. Denied times ("not 3pm") do not. A note can state several facts or none.
- Payment handover: no collection before the stated time; a `release` event comes then.

### 1.7 Handling cars
1. Premium car: experienced driver only. Fine €150 per car.
2. Multi-car gig: at most 12 h driving.
3. EV below 30% charge on a route over 200 km needs a charging stop (`withCharging`). Without: the car is 90 min late and the fine is €100.
4. Delivery only in site opening hours. At a site its stated hours show closed, the driver leaves the car; the delivery counts at next opening, no waiting pay. At a site closed when stated hours show open, the driver waits up to 2 h at €15/h, then leaves the car (delivery counts at next opening).
5. Private delivery: booked hour; deadline = end of the hour + 30 min; early arrival waits free.

### 1.8 Account
| Line | Amount |
|---|---|
| Delivered order | the price you quoted |
| Late ≤ 2 h | 10% of price back |
| Late 2–24 h | 25% back |
| Late > 24 h, up to 2 business days | 50% back |
| Late > 2 business days | whole price back; the car must still be delivered |
| Undelivered at the end (Wed 22:00) | no price, penalty of 2× price |
| Driver fee | paid when the gig is done |
| Failed visit | half the failed car's share of the fee, at least €25 |
| Release | 25% / 50% / 100% of the fee (see 1.4); free after `driver_late` |
| Waiting | €15/h, at most 2 h |
| Fines | premium without experienced driver €150/car; EV without needed charging stop €100 |

Saturday and Sunday are not business days: due Friday, delivered Monday = 1 business day late. **[verify]** how the hours-based tiers treat a Friday-due car delivered on Saturday.

### 1.9 Level 8 specifics
- Drivers: 26–40% of an average world, times a random per-town factor (some towns keep most drivers, some lose nearly all). Read `/drivers` at minute 0 of every world.
- Competitor price = list × lane factor × day factor × world level × small request factor. World level is **+26% to +54%** above list. Part of the lane factor is the same in every world; the rest is new each world. Some mornings its prices for a place move a step; once a week its list reshapes (short and long lanes move in opposite directions). Each morning it looks at each dealer's recent requests: where you won most it lowers its prices, where you won few it raises them (a few steps at most; it learns only win or loss).
- **Every week has:** outage (one working day, 08:00–18:00, competitor down in a town plus places within 80 km; dealers there use a backup about 30% above the competitor); flu (30% of working drivers stay home for a day); bulk order (30–40 cars from one yard); **price war** (one working day without outage, competitor 20% under its usual prices everywhere 08:00–18:00).
- **Trust:** each dealer counts your on-time orders, up to 25. Each raises the price it accepts from you by 1% (25 orders = +25%). A late order halves that dealer's count (rounded down). Starts at 0 each world. Count it from your ledger: an order's revenue line with no late refund = on time.
- A late or undelivered car also makes that dealer accept only lower prices (satisfaction); each on-time order wins a little back. Unquoted requests lower it slightly; losing quotes do not.

### 1.10 API and limits cheat sheet
- Auth: `Authorization: Bearer <team key>` (not needed for map, leaderboards, `/openapi.json`, `/kit/`).
- Practice: `POST /v1/worlds {seed?, level, board?}`, `GET /v1/worlds/{id}` (snapshot), `POST .../actions` (1–50), `POST .../advance` (`to` | `by` | `untilEvent`+`max`, optional `actions`), `GET .../events?after=&limit=`, `GET .../drivers`, `POST .../fork` (403 on ranking runs), `GET .../score`, `GET .../reveal` (after the end; 403 on ranking runs), WebSocket `.../stream?after=seq`, `DELETE`.
- `advance` returns every event since the previous `advance` answer, including events your actions caused. After a server restart answers can repeat events: **dedupe by `seq`**.
- At most 8 unfinished practice worlds (a fork counts as one), 16 streams.
- **Ranking runs:** `board: true` creates the next run (n-th run plays world n). 409 while the level's current run is unfinished, after the 5th run until the next round, or before the first round. `DELETE` on an unfinished run does not remove it: it runs to its end without your system and counts. `GET /v1/leaderboards/practice?level=n` (no key) shows the current and previous rounds, all teams, including `house-` teams, with per-run `marginCents`, `onTimeShare`, `wonOrders`, `ranked`.
- **Final:** `GET /v1/final` (404 until set), `GET /v1/leaderboard` (server-sent events, no key, every 2 s). `advance`, `fork`, `DELETE` give 403; `reveal` opens after the end.
- **Buckets:** practice = 1 token per request whatever it carries (a batch of 50 actions costs 1), up to 1,000/s for a team (about 170 at 60 teams, 50 at 200, **20 while a final or test final runs**). Final actions: 20/s, bucket 50, 1 token per action. Final reads: 50/s, bucket 50, 1 token per GET and per stream opened. Final requests over the limit get 429 at once and cost nothing. Headers `RateLimit-*` tell when the next token arrives.
- **Errors:** 400 (with `field`), 401, 403, 404, 409, 429 (`Retry-After` ms), 502/503/504 = server restarting (retry, re-read state). An action that parses but cannot be done returns `{ok:false, reason}` inside a 200.
- **Throughput:** a level-8 starter week is about 1,891 requests: about 2 s on a quiet server, 11 s at 170 req/s, 38 s at 50 req/s. Parallel runs of one team share the bucket; fewer requests per week helps more than more parallelism.

### 1.11 Final clock
- Weekday hour (06:00–22:00) = 18 real s; Saturday 6 s; last Monday 9 s; night, Sunday and after the last Monday 3 s. About 34 min in total.
- 15-min quote window = **4.5 real s** in the day. A 10-min offer = **3 real s**.
- If the code stops, the world continues: gigs keep fee schedules, drivers keep driving, requests go to the competitor. The server may restart mid-final; the system must survive that.

---

## 2. Economics and strategy

### 2.1 Scale
- The starter's level-8 week: €71,332 revenue over 949 orders, so about **€75 per order**. It ends at −€72,612.51 with 45.5% on time. The judging page's example (+€12,551/week vs −€67,177 for the starter over 20 level-8 weeks) shows the form and scale of evidence; it is an illustration, not necessarily House best.
- Fines (€150, €100) are worth 1–2 orders each; a failed visit costs at least €25. Treat constraint compliance as hard.

### 2.2 Value-of-time cliffs (price P = €75)
| Outcome | Cost vs on-time | Step from previous |
|---|---|---|
| ≤ 2 h late | €7.5 | +€7.5 |
| 2–24 h late | €19 | +€11 |
| ≤ 2 business days late | €38 | +€19 |
| later | €75 | +€38 |
| undelivered | €225 (lose P, pay 2P) | +€150 |

Lateness is cheap in euros up to 2 h, expensive after two business days, catastrophic if undelivered. Any lateness also counts against the 90% minimum and halves that dealer's trust count. **Lateness is a budget, not a failure:** up to about 10% of orders may be late and you are still ranked.

### 2.3 Two shadow prices
- **λ(region, day):** the price of a scarce driver. Added to cost in quotes and fees.
- **μ:** the price of one late order against the 90% gate.
- Expected lateness cost of order o:
  `L(o) = P·(0.10 q1 + 0.25 q2 + 0.50 q3 + 1.00 q4 + 3.00 qU) + (1 − q0)·(T_o + μ)`
  where q1..q4 are the probabilities of each lateness tier, qU of undelivered, q0 of on time, and `T_o` is the trust cost.
- **Trust cost:** `T_o ≈ 0.01·(k_d − ⌊k_d/2⌋)·V_d`, where k_d is the dealer's on-time count and V_d the expected future quoted value from that dealer. It falls to 0 after the dealer's last request. Example **[hyp]**: k = 20 and about €1,000 of future value gives T ≈ €100, more than the refund.
- **Quote rule:** subtract `L(o)` (and the expected fee, extras and λ) from margin.
- **Fee rule:** pay an extra Δf only if Δf is less than the drop in `L(o)` it buys. If an order would otherwise end undelivered, fees up to about 2P are justified.
- **μ controller (every world hour):** `μ ← clip(μ·exp(η·(ŝ − τ)/τ))`, where ŝ is the projected late share and τ the target (start at 6%). Tune on seed variance so that P(on time < 90%) is negligible.

### 2.4 Quote rule
`p* = argmax over p of P_win(p)·(p − C)`, with `P_win(p) = σ(−κ·ln(p / ĉ_eff) + v_option)` and `ĉ_eff = ĉ·(1 + 0.01·k_d)·s_d` (trust and satisfaction). Search `p` over 0.9–1.9 × list. Decline if EV ≤ 0, if a constraint cannot be met (e.g. premium car where no experienced driver is in range), or if the governor gate is closed.

### 2.5 Selectivity dividend [hyp]
The competitor learns only whether it won each request. Declining by quoting high is free and looks like a loss to it. Where you win few of a dealer's requests it raises its prices, which raises your price ceiling on the requests you do take. Winning most cuts its prices. **Test:** per-dealer win rate at a fixed price ratio versus the previous day's win share, over several weeks.

### 2.6 Pooling and relay offers [hyp]
- The 12 h limit counts deadhead drives, so a reverse pair (A→B then B→A) has no deadhead and no ticket home. Trade-ins are this by construction.
- **Pooling:** hold `next_day` and `within_3_days` orders unposted while a reverse-lane partner may arrive, bounded by `lastPickupAt` minus a buffer. Holding does not age the gig (the age clock starts at first posting).
- **Relay offers:** on `delivered` the driver's position is known. Offer an open gig whose pickup is near that place at the driver's marginal cost, below the app fee.

### 2.7 Soft windows [hyp]
An explicit delivery-stop window extended 1–2 h past the order's window caps lateness inside the 10% tier and lets drivers who cannot be on time cheaply take the gig at a lower fee. Without windows, a stop that no driver can reach in time runs to the end of the world, so nothing needs to end undelivered. **Test with `fork`:** the same order with a strict window and with +2 h; compare booked fee and realised lateness.

### 2.8 Notification economics
- A driver is notified once per order, within 30 km of home, never 23:00–07:00; a raise never notifies; drivers learn booked ÷ first viewed fee and time to book.
- So the **opening fee matters most.** Post **once**, at the estimated clearing fee, in daytime. Do not post low and ramp, and do not post early just because you can (it ages the gig). Hold night wins until 07:00 unless the pickup comes earlier.
- Keep booked ÷ first-fee close to 1 across orders; use few ramp steps only for drivers who re-check. A downward `reprice` is allowed, so overshoots are fixable.

### 2.9 Supply map
Rebuilt at minute 0 of every world from `/drivers`: per town, drivers, drivers within 30 km (notified pool), experienced drivers (premium capacity), manual licences, past drops. Delivery-town driver counts give the cheap-return signal. Decline pickups in empty towns unless the fee covers the whole trip, or reach them by offers.

---

## 3. Architecture and modules

```
Stream (WebSocket) -> EventStore -> State
   State -> NoteReader, Pricer, Dispatcher, Watchdog, Governor
   all actions -> ActionQueue (20 actions/s, priority) -> API
```

Implementation notes: Python 3.9+ with the kit; every decision a pure function of state, RNG seeded by request or order id; JSONL logs; unit tests for pure functions; no secrets in the repo; git tag per release.

Each module lists **Does / Checks / Expect / Valid when**. Thresholds are targets to calibrate on the first 10 practice weeks, then freeze as acceptance tests.

### M1: Transport and ActionQueue
- **Does:** sole API gateway. Priorities: P0 quotes, P1 deadline-critical fees and offers, P2 new gigs, P3 housekeeping. Mirrors the final buckets, batches at most 50, retries after 5 s on `Unreachable`/502/503/504 with a state rebuild, dedupes, pre-flights (integer cents and minutes, no quote at or after `respondBy`, no reprice or withdraw on a booked gig).
- **Checks:** every result `ok`, `reason` logged; quote slack; queue depth; 429 count.
- **Expect:** average action-bucket use below 50%; a bulk burst (30–40 quotes) fits one batch; about 0 429s.
- **Valid when:** a final-pace simulation (4.5 s per quote window, 20 actions/s, +150 ms RTT) misses 0 quotes; failures below 1% and all legitimate races; a 10 s network cut plus kill leaves no duplicate gigs and no lost orders.

### M2: EventStore and State
- **Does:** append-only event log, derived state, `rebuild()` from snapshot + events, dedupe by `seq`, per-order P&L from `ledger`, per-dealer on-time counters.
- **Checks:** `seq` contiguous; ledger sum equals `score()` at day boundaries; each order in exactly one state; each open order has a plan.
- **Valid when:** the starter's printed daily margins are reproduced to the cent on `spread-1`; a kill and restart at 10 random points gives an identical final margin on a fixed seed (**restart-invariance**).

### M3: World knowledge
- **Does:** map, roster at minute 0, supply map (2.9), lane cheap-return score, hourly roster refresh.
- **Valid when:** Spearman ρ ≥ 0.4 between the supply index and mean booked ÷ typical fee per pickup town over at least 20 weeks; first-viewer distances in `views.csv` match the 30 km rule.

### M4: NoteReader
- **Does:** grammar parser (1.6) outputs earliest pickup, release time, pickup and delivery hours, deadline override, manual, plates, summer tyres, delay days, confidence, provenance. LLM fallback (strict JSON, 1.8 s timeout) for typos and paraphrase. Merge keeps the more restrictive reading. Re-parse at `order_won` with a stronger model.
- **Checks:** dates in the future; weekday 2–6 days ahead; word-hours in 9–17; corrections and denials handled.
- **Expect:** reads most notes; low confidence on a risky note means a premium or a decline.
- **Valid when:** on at least 500 labelled notes (label harvest, E4) recall ≥ 0.95 on gearbox, plates, tyres and ≥ 0.90 on dates and times. Live: 0 `licence`, 0 `no_plates`, `not_ready` + `closed` under 0.5% of orders. LLM p95 under 1.8 s, fallback rate under 10%.

### M5: Constraint layer and gig builder
- **Does:** builds gigs from order, note and request attributes: stops and windows, `withPlates`, `withCharging` (EV under 30% charge and route over 200 km), manual flag, experienced audience for premium, trade-in as one gig, grouping within 12 h, server's `lastPickupAt`.
- **Checks (pre-post):** windows consistent and not already ended; at most 12 h; no live gig for the same car; schedule non-decreasing.
- **Valid when (20 weeks):** 0 fine lines in the ledger; 0 controllable `visit_failed`; `gig_expired` under 3% of gigs; 0 rejected posts.

### M6: Pricer
- **Does:** two-phase quoting. Phase 1 within about 0.5 s (grammar-only parse, conservative cost with a risk premium). Phase 2 replaces it before `respondBy` with the refined quote. Per option: cost (2.3), `ĉ_eff` (M7), `p*` (2.4). Modifiers: trade-in and pool credit, trust tolerance, exploration dither of ±5% on low-stakes requests (seeded by request id). Slower options may be priced lower when they enable pooling. Never quote an option the dealer did not offer.
- **Checks:** integer cents, finite, at least one price, slack to `respondBy` of at least 1 s.
- **Expect:** clearly fewer wins than the starter's 949 orders at a higher mean price ÷ list; median accepted `p/ĉ` of about 0.93–0.99; margin above 0 on at least 85% of won orders.
- **Valid when:** calibration within ±8 points per probability bin over at least 2,000 quotes and Brier score at least 10% better than a constant win rate; paired profit beats list-price quoting (same dispatcher) on at least 90% of 20 dev seeds with no rise in late rate.

### M7: Competitor model
- **Does:** posteriors for world level W (L8 prior 1.26–1.54), day factor, lane factor (prior from sweeps), dealer sensitivity κ_d, option value; trust and satisfaction terms; logistic-loss update at every `order_won` and `order_lost`, with forgetting; per-dealer drift term for selectivity.
- **Checks:** W stays in [1.2, 1.6] after day 1 (alarm outside [1.1, 1.7]); no NaN or negative prices.
- **Expect:** converges in about 1.5–2 business days (150–250 resolved quotes).
- **Valid when:** online log-loss beats the static prior on at least 80% of seeds; margin gain at least 0 on at least 85%; day-2 W within ±5% of a ladder-week reference on the same seed.

### M8: Event detectors
- **Price war:** run of losses beyond what `P_win` predicts on a working day; adjusts today's day factor (not a special mode); resets at 18:00.
- **Outage:** unexpected wins by dealers in one geographic cluster; raise tolerance there (backup about +30%).
- **Flu:** falling views and bookings, rising time to book; raises λ.
- **Bulk order:** 30–40 requests from one yard; price as a block against local supply, decline all or accept only what supply absorbs.
- **Expect:** price war flagged within the first 1–2 world hours of the day; flu within about 3 hours.
- **Valid when (20 seeds):** war day agrees with a probe week (E6) on at least 90% of weeks; median delay at most 90 world minutes; at most 1 false alarm per week; war-day margin with detector at least without it on 85% of seeds; bulk block on-time at least 90% or declined, and margin at least 0 on 80% of bulk weeks.

### M9: Capacity λ and pooling
- **Does:** λ per region-day (`a·max(0, demand/supply − τ)²·typical_fee`), supply from roster × P(work), learned from views, bookings, drops (×0.7 on flu); hard cap per region-day; pooling per 2.6 with pair search among open orders (same corridor, opposite direction, compatible windows, at most 12 h).
- **Checks:** λ ≥ 0, monotone in load, resets daily; a held order never misses its post-by time.
- **Valid when:** corr(λ at quote time, realised booked ÷ typical fee) ≥ 0.4; λ-off is worse on at least 75% of seeds; pooling lowers fee per car versus singles with no on-time loss (paired CI above 0).

### M10: Fee engine
- **Does:** opening fee = estimated clearing fee (about the 50th percentile of the learned model); at most 3 meaningful steps; cap from 2.2 and 2.3; posting-time rules (2.8); `reprice` on drop, no-show, `driver_late`, expiry and `deadline_close`; model learned from bookings, views and drops; slight randomisation.
- **Checks:** non-decreasing; at most 48 steps; no post before 07:00 or after 23:00 unless the pickup requires it; booked ÷ first-fee ratio drift.
- **Expect:** typical-fee gigs often do not book in driver-poor towns; booked ratios above 1 there.
- **Valid when:** at least 97% of orders booked at least 3 h before `lastPickupAt`; versus the starter's ramp, at least 10% lower fee spend at equal on-time (or higher on-time at equal spend); slope of log time-to-book over the week at most 0; predicted booking probability within 1 h of posting is calibrated.

### M11: Offers
- **Does:** up to 3 open offers per gig, at most 3 per driver per day (own counter), 07:00–23:00 only. Candidates: drivers seen working today (viewed, booked or finishing one of your gigs), near pickup or home, by rating and drops. Fee about estimated cost × 1.05. Relay offers on `delivered`. Fallback to the app.
- **Checks:** counters; no offer 23:00–07:00; offered fee at most the expected eventual app fee.
- **Valid when:** net saving above 0 on at least 70% of lanes used; won-to-booked time not longer than app-only; offers on/off at least 0 on paired seeds.

### M12: Watchdog
| Event | Handler |
|---|---|
| `gig_expired` | repost within 2 world minutes; stops without windows run to the end of the world |
| `gig_dropped`, `no_show` | check the schedule can still find a driver before the pickup; reprice if not |
| `driver_late` | keep if `pickupAt` still meets `lastPickupAt`, else release free and rebook |
| `visit_failed` | repost with the cause fixed (ready time, hours, `withPlates`, licence) |
| `order_changed` | replan, reprice, recheck `lastPickupAt` |
| `order_cancelled` | handle `withdrawn` / `released` / `shortened` / `continues`; repost surviving cars |
| `deadline_close` | tier-aware fee escalation plus offers |
| `forecast` | expect slower drives and snow drops |
| hourly sweep | every open order has a live plan |

- **Checks (invariants after each event):** every undelivered, non-cancelled order has a live gig, a booked driver, or is delivered; no negative time to `lastPickupAt` without escalation.
- **Valid when (20 weeks):** 0 invariant violations; every trigger event answered within its deadline; **0% undelivered at the end**.

### M13: Governor
- **Does:** per-order lateness-tier probabilities q; projected late share; μ controller (2.3); planned-late soft windows (2.7); emergency mode (quote high on everything new if projected on-time falls below 90% with little time left); kill-switch.
- **Checks:** calibration of q on at least 3,000 order-time snapshots (Brier score, slope 0.8–1.2); day-3 projection error at most 3 points.
- **Valid when:** ranked on 40/40 dev and hold-out seeds with minimum on-time at least 91%; soft windows keep lateness inside the ≤ 2 h tier for at least 80% of planned-late orders; budgeted versus strict-on-time ablation shows margin CI above 0 and no drop in ranked count; governor margin cost under 2% when it does not bind.

### M14: Harness and optimizer
- **Does:** `spread_sweep.py` runs paired seeds in parallel, parses the starter's `End` line into SQLite, compares versions with a paired bootstrap, prints ACCEPT only if the CI lower bound is above 0, ranked weeks do not drop and minimum on-time is at least 91%. Dev seeds `dev:20`, hold-out `hold:20`. Optimiser (random search, then CMA-ES or Bayesian) on about 12 parameters, objective: mean margin − 5,000 × (seeds with on-time below 92%), also report the 20th percentile.
- **Rules:** same seeds for both versions; any change reshapes the rest of the week, so only paired multi-seed results count; touch hold-out once per release candidate; a feature is accepted from at least 20 seeds; **no sweeps during test finals or the final** (practice bucket drops to 20/s).
- **Valid when:** the same seed and parameters give an identical margin twice; the self-test passes (`python spread_sweep.py selftest`).

### M15: Ops
- **Does:** terminal dashboard (margin to date, orders won/open/at-risk, projected on-time, queue depth, 429s, event lag, LLM latency, detector states, live rank from `GET /v1/leaderboard`); manual commands (pause quoting, force reprice, release, dump snapshot); auto-restart; run on a Stockholm cloud VM (AWS eu-north-1 or GCP europe-north2).
- **Valid when (Test Final 2):** panel margin within €1 of the server's score; kill-switch effective on the next request; restart to running in under 10 s.

### M16: Evidence and submission
- **Does:** ablation table, calibration plot, price-war detection timeline, architecture slide; one command regenerates every number.
- **Valid when:** every number on a slide has a seed set and run id behind it.

---

## 4. Experiments catalog

| ID | What | How | Used for | Accept |
|---|---|---|---|---|
| E1 | Reproduce the starter | `spread-starter --level 8 --seed spread-1` (also L7, L6) | M2 | End line matches to the cent |
| E2 | Study week | `spread-reveal-csv --seed study-1` | dealer concentration (do the top 20 dealers hold half the requests? if not, drop the trust ramp), option mix, trade-in share, notes share, typical-fee distribution, arrival curve | numbers recorded |
| E3 | Board baseline | `curl -s "$SPREAD_URL/v1/leaderboards/practice?level=8"` | House best's `wonOrders`, margin, on-time per world | targets set |
| E4 | Label harvest | level 5, quote about 0.5× list on every request, run to the end, reveal | score the NoteReader on `legs.csv` | M4 recall targets |
| E5 | Ladder weeks | quote ratio ∈ {1.0, 1.15, 1.3, 1.45, 1.6} × list across requests | win curve per lane bucket, M7 prior | calibration (M6) |
| E6 | Probe weeks | fixed ratio 1.35 on all requests | war day and outage region ground truth | M8 agreement |
| E7 | Selectivity drift | per-dealer fixed-ratio win rate vs previous day's win share | 2.5 | slope significant, or cut |
| E8 | Pooling ablation | pooling on/off, same seeds | 2.6 | fee per car lower, on-time not lower |
| E9 | Soft-window fork test | `fork` at order win; strict window vs +2 h | 2.7 | lateness stays in the ≤ 2 h tier, fee lower |
| E10 | Fee-clearing fork lab | fork K copies at a decision point with K fee schedules for one gig, advance, record which book | labels for M10 (optional) | model error improves |
| E11 | Restart-invariance | kill and restart at 10 random points on a fixed seed | M2 | identical margin |
| E12 | Final-pace simulation | 4.5 s per window, 20 actions/s, +150 ms RTT | M1 | 0 missed quotes |
| E13 | Stress seeds | flu-heavy, bulk-heavy weeks; slow network | M13, M1 | ranked on all |

---

## 5. Acceptance gates

| Gate | Pass condition |
|---|---|
| **G0** plumbing | E1 reproduces to the cent at L6, L7, L8 |
| **G1** baseline | L6: at least 90% on time and margin ≥ 0 on 5 seeds; 0 controllable failed visits; 0 fines |
| **G2** core | L8 ranked on 10/10 dev seeds; margin clearly above the starter; M6 calibration passes |
| **G3** adaptivity | M7–M11 and M13 each win their ablation (paired, CI above 0) |
| **G4** hold-out | 20/20 ranked; 20th-percentile margin at target; compared with House best on ranking rounds |
| **G5** live | both test finals: 0 missed quotes, 0 invariant violations, dashboard reconciles |
| **G6** final | actual run recorded and ranked; see the timing postmortem (the final began at 01:00 EET, not the planned 08:00) |

---

## 6. Schedule (Helsinki)

Assumption **[verify via `client.board`]**: a ranking round stays playable until the next one opens. Each round's five worlds can be played once, so spend rounds on candidate versions; run experiments on your own dev seeds.

| When | Event | Plan |
|---|---|---|
| Fri 18:00 | Opening ceremony | read the docs, install the kit |
| Fri 19:30 | Hacking starts; round 1 | E1, E2, E3; do not burn round 1 with the unmodified starter unless you want the baseline |
| Fri 23:59 | **Preliminary submission** | team hash (team page), repo link, 1–3 draft slides |
| Sat 00:00 | Round 2 (long window) | play v1; start an unattended optimiser on dev seeds; sleep |
| Sat 09:00 / 12:00 | Rounds 3, 4 | v2 with λ, μ, offers. Submissions open at 12:00 |
| Sat 13:45–14:00 | Registration pauses | **Test final 1** at 14:00 (about 19 min, level-8 week from Thursday 00:00), run from the VM |
| Sat 15:00 / 18:00 | Rounds 5, 6 | fixes from test final 1; hold-out sweep |
| Sat 19:45–20:00 | Registration pauses | **Test final 2**: rehearsal with the frozen candidate |
| Sat 21:00 | Round 7 | release candidate; code freeze about 22:00; write slides |
| Sun 00:00 / 03:00 / 06:00 | Rounds 8–10 | soak only; bug fixes only. Sleep about 02:30–06:30 |
| Sun 15 Nov 01:00 EET | **Final actually started** (`startsAt=2026-11-14T23:00:00Z`) | official `/v1/leaderboard`; old planned 08:00 time was stale |
| Sun 15 Nov ~01:34 EET | Final ended (`now=endsAt=14280`) | ranked 36th; 212 requests had closed before attachment |
| Sun 10:00 | Submissions close | hash, code link, deck. Every team submits |
| Sun 10:30–14:00 | Jury meets the top 10 | present |
| Sun 14:00 / 15:10 | Ceremony / winners | |

---

## 7. Final-day runbook

The planned 07:30/08:00 schedule was stale: the official final feed reported a 01:00 EET start. For any live event, start the supervisor before the announced window and verify the actual world from `/v1/final` and the live board; do not wait for a hard-coded clock time.

**Pre-flight (before the live final window)**
1. VM up, clock synced, `.env` present, LLM key valid, disk free.
2. Latest tag checked out; unit tests and `selftest` green.
3. `client.final()` may keep returning the previous final after it ends; check `now < endsAt` before joining.
4. Start the system (`--final` style runner); confirm the stream is open and the snapshot rebuilt.
5. Dashboard shows margin, rank (SSE leaderboard), queue depth, quote slack.
6. Kill-switch tested (quote high on everything new, keep serving open orders).

**During the final**
- Do not run practice sweeps (practice bucket is 20/s while a final runs).
- If the stream drops, the client reconnects with `after=seq`; verify no gap.
- If the process dies, restart: it rebuilds from `snapshot()` and `events()`; the world keeps going on existing fee schedules. A 502/503/504 means the server is restarting: wait 5 s, re-read state, continue.
- If projected on-time falls below 90%, engage emergency mode.

**After**
- Reveal opens when the final ends. Record the result and the best ranking-round result for the deck.

---

## 8. Jury pitch

Rubric: **elegant** (few parts, each with a reason), **clear** (decisions you can state), **creative** (a way of seeing dealers, drivers or the week that was not expected), **robust** (many unseen weeks, restart, slow network, surprises).

### Five headline ideas (slide format: idea, why, effect)
| Idea | Why (what you saw) | Ablation, same seeds |
|---|---|---|
| 1. Price to the competitor, learned online | competitor is 26–54% above list; starter quotes list | list-price quoting vs learned pricing |
| 2. Win cars by where drivers are (λ, pooling, bulk) | cost depends on driver homes; some towns lose nearly all drivers | λ off; pooling off |
| 3. Lateness as a budget (μ) and soft windows | ≤ 2 h late costs 10%; the gate allows about 10% late | strict on-time vs budgeted |
| 4. Fees that do not teach waiting, and relay offers (≤ 3 per driver per day) | drivers learn fee ramps; notification is once per order | starter ramp vs learned opening fee; offers off |
| 5. Restart-invariant event-sourced core | the final must survive restarts | kill/restart test; results over 40 weeks |

Trust ramp and selectivity are extra ideas **only if** the data supports them (E2, E7); otherwise cut. At most five ideas.

### Deck (5–7 slides)
1. Answer first: final result, best ranking-round result, big ideas.
2. The problem as three coupled decisions: quote, fee, dispatch.
3–5. One idea per slide: claim, evidence (margin and on-time share with and without, same weeks, with units and a comparison).
6. How it decides (formula or diagram, not code screenshots); restart design.
7. What did not work; what would break it; what we do not know.

Rules from the judging page: use the challenge's words (dealer, request, gig, fee, typical fee, deadline); one idea per slide; every number with unit and comparison; cut filler; if an agent wrote slides, read every line.

---

## 9. Open items

1. Action JSON shapes (`quote`, `post`, `offer`, `reprice`, `withdraw`, `release`): need `spread/types.py` or `/openapi.json`.
2. Request fields for premium, EV charge level, gearbox; payloads of `delivered` and `picked_up` (driver id, place).
3. Largest accepted decline price (is there a cap?).
4. Whether hours-based lateness tiers count weekend hours (Friday-due car delivered Saturday).
5. Refund and 90% accounting for two-car orders (per order or per car).
6. When the 3-offers-per-day counter resets.
7. Ranking round window semantics (see section 6 assumption).
8. About 40 real notes from `study-1` for the grammar parser.
9. House best's per-world numbers from the public board (E3).

---

## 10. Changelog and decision log

| Date | Change |
|---|---|
| 13 Nov 2026 | v1: consolidated analysis and plan; rules, API and handbook digested; modules M1–M16 with acceptance tests; experiments E1–E13; gates G0–G6; schedule and runbook. |
| 13 Nov 2026 | v1.1: every claim checked against RULES/API/HANDBOOK/openapi/kit (286 claims: 220 confirmed, 50 corrected, 16 not in docs), each correction upheld by an independent skeptic. **`docs/spec_delta.md` overrides this file where they differ.** §9 items 1, 2, 3, 5, 7 answered there; items 4 and 6 need a practice-world test. Spot-checked by hand: action shapes vs `types.py`, `/v1/final` after an ended final, stream handshake errors, reprice only when unbooked, notes from L5. |

| Date | Decision | Evidence (seed set, run ids) |
|---|---|---|
| 13 Nov 2026 | G0 passed. "1,891 requests" (API.md) counts `advance` steps only; the starter's L8 week sends 2,490 requests in all (+587 `POST /actions` from mid-step sends, +12 create/snapshot/score). Budget throughput (M1) on 2,490, not 1,891. | spread-1, two identical passes. Latest (after review fixes): L8 w679feb4906e71e6b684f (CLI), w7f773eb64e9abb1827bd (counted); L7 wd10b38ea14bf155c6acd; L6 w80b1d9d054900e3891a2. First: L8 w76bbd07a816e778d7144 |
| 13 Nov 2026 | L6 starter is already ranked on spread-1 (95.9% on time, −€1,172.51): G1 is a margin problem at L6, not an on-time one. | same L6 run |
| 14 Nov 2026 | **Root cause of "non-deterministic" weeks: the kit client resends POSTs on a flaky network.** On this machine's unstable network (DNS failures and resets also hit the Anthropic API), `spread/client.py:170` resent requests whose connection broke *after* they reached the server. The server applied them twice: duplicate gigs for one car (g354/g355 in wc604…), a clock moved twice, and the first answer's events lost (seq gaps; clean weeks have 0 gaps in 179,047 events). The world itself is deterministic. Decisions: (1) `desk/client.py` SafeClient resends only reads and POSTs that never left; any other break is `Unreachable`, recovered by WorldIO from the snapshot and event log; (2) `WorldIO` also fills any seq gap from `GET /events` (no cost on clean answers); (3) sweeps and restart tests run a canary (kit starter, spread-1 L8, must match the handbook) to flag network trouble; (4) run the final from a VM with a stable network (spec M15), never with the kit client's resend. | evidence/restart/result_server_incident_0336.json; runs wc60488276dab50f68fe0 (gap 16220→16283 refetched: 58 views, 2 ledger, 1 order_won, 1 delivered) |
| 14 Nov 2026 (evening) | After test final 2 (rank 62/75, 337 of 1030 requests declined): final policy = step 7 + `options=safe max_drive_h=6 min_slack_h=8 night_hold=1`. Chosen on 8 tuning weeks (push3-7: 40 arms), confirmed on 16 fresh weeks (holdout9). Rejected: drives ≥ 7 h (worst week 90.5-90.7%), long-drive early/high fee caps, batch cap, opening fee 0.8×, intake cap 100-120, win target 0.45-0.5, lane price factor (≈ €150/week, below sweep resolution). | evidence/sweeps/push3-7.json, holdout8-9.json, rehearsal/wfe15af4fc63548624f3e.json |
| 14 Nov 2026 | Policy evidence so far (L8, deadline fees, 1.5× list, decline if slack < 6 h or drive > 5 h): dev seeds 4/4 ranked, +€19,193; hold-out 4/6 ranked, +€39,844. Fixed thresholds do not generalise to every world: an in-week adaptive rule is needed. | evidence/sweeps/select1.json, holdout1.json (holdout1 ran during server incidents: 16/18 runs resumed in-process) |
| 14 Nov 2026 | **Adopt the trust markup** (quote × (1 + 0.01 × the dealer's on-time count), RULES.md:163-165) on top of v3. 8 fresh seeds, canary clean, SafeClient: v3 8/8 ranked, +€71,062, worst 91.5%; v3+trust 8/8, +€71,623, worst 94.1%, 22% fewer orders. Same margin, 2.6 points more buffer on the worst week. Caveat: holdout1's two failures (4/6) ran before SafeClient during the double-send period; to be rerun. Test final 1 plays v3+trust. | evidence/sweeps/trust1.json |
| 14 Nov 2026 | **Adopt the adaptive price (C)**: start at 1.5×, steer toward 40% of real quotes won (±4% per update, every 30 min, ≥ 5 new outcomes), floor at typical fee × 1.15, push up at ≥ 80 wins in 24 h. 8 full weeks incl. the 4 hardest seeds: C 8/8 ranked, +€68,183, worst 94.8%; fixed 1.5× 8/8, +€66,209, worst 93.3%. 4 Thursday-start weeks: C +€9,738 vs +€7,724. Rejected E (slack 4 h): +€70,033 but hold-5 87.8%. Trust markup is a trade (less margin, more buffer at the 30% target). Holdout1's failures were artefacts (hold-2/5 ranked now). Live rehearsal (2×, kill): 126 orders, 98.4%, +€2,620; 9 of 10 unanswered requests fell in the kill's downtime, 1 quote waited 1.39 s behind a slow answer (2.25 s window at 2×). | evidence/sweeps/adapt1.json, adapt1_thu.json, evidence/rehearsal/wa00509102ad30f053b32.json, proof/adapt.html |
| 14 Nov 2026 | **Final candidate (user's choice): C with opening fee 0.9× typical.** Same 8 weeks: +€74,009 vs C +€68,183 (+8.5%), 8/8 ranked, worst week 92.5% vs 94.8%. Pre-registered rule: worst ≥ 92%, then margin. Safer alternative kept on file: 0.9× + intake cap 70 (+€72,289, worst 92.8%). Live rehearsal (tf-9, 2×, kill): 128 orders, 99.2%, +€3,151 vs C +€2,620. In tools/start_final.sh for test final 2 and the final. | evidence/sweeps/push1.json, push2.json, evidence/rehearsal/w86c69515c211d2cace4c.json, proof/push.html |
| 15 Nov 2026 | **Final-day fee-cap update: use `fee_cap=1.85`.** Paired fee-cap sweep on six seeds; independent validation on 16 new L8 weeks: cap 1.85 ranked 16/16, worst 92.41%, margin €148,177; cap 2.0 ranked 16/16, worst 93.01%, margin €140,585. The 1.85 cap gained €474.55/week and won 14/16 paired seeds; canary clean. A 1.75 cap gained €336.20/week across 24 fresh seeds but dipped to 91.97%, so it did not meet the 92% buffer. Adaptive-controller response retunes also failed independent validation and remain at their original values. | `tools/sweep_feecap2.sh`, `tools/sweep_feecap_hold3.sh`, `evidence/sweeps/feecap2.json`, `feecap_hold3.json`, `feeprice_hold1.json`, `feeprice_hold2.json`, `response1.json`, `response_hold1.json` |
| 15 Nov 2026 | Final placed 36th; ranked at €5,912.57 and 94.42% on time (251 won orders, none undelivered). 212 of 1,036 requests had passed before desk attachment at world minute 1205; all 824 seen requests were quoted at 0.096 s p99. Operational priority for any rerun: attach before the first requests close. | final `f88a11d932a63ddb3f413`; `evidence/final.json`, `runs/f88a11d932a63ddb3f413/live_summary.json`, public `/v1/leaderboard` |
| 15 Nov 2026 | Reject `max_drive_h=6.5` for future runs. Eight-seed screening gained €375.96/week, but fresh 16-seed paired validation gained only €196.73/week, won 9/16 pairs, ranked 15/16 (87.33% worst); the baseline ranked 16/16. Keep the 6 h limit. | `tools/sweep_safety1.sh`, `evidence/sweeps/safety1.json`, `tools/sweep_safety_hold1.sh`, `evidence/sweeps/safety_hold1.json` |
| 15 Nov 2026 | **Adopt `min_slack_h=7` for future runs.** Fresh paired validation: 16/16 ranked, worst 92.62% on time, €169,285 total margin; the 8 h control was 15/16 ranked, worst 88.93%, €165,592. Gain €230.81/week, 10/16 paired weeks higher; canary clean. The completed final used 8 h. | `tools/sweep_safety1.sh`, `evidence/sweeps/safety1.json`, `tools/sweep_safety_hold2.sh`, `evidence/sweeps/safety_hold2.json` |
| 15 Nov 2026 | Ran Season 10's five ranking worlds at every level with the same L8 policy (40 runs). L8: €50,220, rank 52 vs Juhus at €102,581.93 on the same seeds; order volume was 1,574 vs 2,367 and on-time 96.44% vs 97.30%. L2–L8 ranked 5/5. L1 was unranked 0/5; the first week won 980 orders but delivered only 79, generating 901 undelivered and −€149,363.74. At that time, the next step was to build level-specific handling before another L1 ranked run. | `tools/rank_all.py`, `evidence/ranking_current/season10.json`, `evidence/l8_season10_top.json` |
| 15 Nov 2026 | L1–L3 follow-up found two causes behind the low-level board losses: 1,021 of 1,106 L1 post attempts used an invalid six-step fee schedule (L1 permits one), and a high-price decline still wins at L1–L3 because dealers ignore price. Fixed L1 to use one fee step and low-level declines to send no quote. L1 capacity sweep rejected caps; a 0.85× one-step fee, 4 h drive limit and 7 h slack averaged €5,754 / 97.23% on time across four fresh holdouts (worst 94.17%). Corrected L2 and L3 policies each ran four practice weeks: €3,448 / 97.7% and €3,971 / 97.4% averages. The ranking runner now uses the L1-specific profile. Practice evidence only; Season 10 scores are unchanged. | `tools/sweep_l1_capacity.sh`, `tools/sweep_l1_margin_v2.sh`, `tools/sweep_l1_holdout_v3.sh`; `evidence/sweeps/l1_capacity_v1.json`, `l1_margin_v2.json`, `l1_holdout_v3.json`, `l2_decline_v1.json`, `l3_decline_v1.json` |
