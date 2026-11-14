# Spec delta: `spread_spec.md` v1 checked against the sources

**What this is.** Line-cited differences between `docs/spread_spec.md` and the sources. `spread_spec.md` is not edited.

**Sources.** RULES.md wins where sources differ. The others are API.md, HANDBOOK.md, `openapi.json` and the kit.
- `openapi.json` is a single line, so it is cited as `openapi.json:1` plus the schema path.
- Kit files (`types.py`, `client.py`, `stream.py`, `starter.py`, `reveal_csv.py`) are under `.venv/lib/python3.13/site-packages/spread/`.

**Refs.** "§x lN" means `spread_spec.md` line N.

**Review status.**
- Section 1 holds only corrections the skeptic upheld, in the skeptic's final wording.
- Every partly verdict had a ruling, so no item is marked "unverified". No claim was marked contradicted.
- Section 4 is the reader's list and was not reviewed by the skeptic, except where marked *ruled*.

---

## 1. Corrections (50 upheld claims in 46 rows, most impactful first)

| # | Spec ref | Spec says | Sources say | Source | Impact |
|---|---|---|---|---|---|
| 1 | §1.10 l118; §7 l355 | `GET /v1/final` gives 404 until the final is set, i.e. before 07:30. | It gives 404 only before any final has ever been set. Each test final is set for every team 15 min before its start, and the route keeps returning the last final after that final ends. So from Sat 13:45 the route returns 200: test final 1, then test final 2 from 19:45, then the ended test final 2 until the real final is set at Sun 07:30. Guard with snapshot `now < endsAt`, or with `ended` in `GET /v1/worlds`, as the starter's `next_final` does. Each call costs a final-read token. | API.md:117; HANDBOOK.md:123, :140; API.md:13, :130 | Critical. Pre-flight can attach to an ended test final. |
| 2 | §7 l362 | "The client reconnects with `after=seq`." | The kit's `World.stream` reconnects only on `OSError`/`Unreachable`: it retries 1 s apart and gives up after 60 failures in a row. Some failures escape it: (a) a refused handshake, such as a 429 when final reads are empty (the handshake skips the token wait) or a 409 at 16 streams, raises a plain `SpreadError` that ends the generator; (b) close code 1000 ends it silently; (c) the starter's outer loop catches only `Unreachable`. Supervise the stream yourself: on any error or early end, reopen it with the last seq. | client.py:239-243; stream.py:35-37, :53-54; starter.py:399; API.md:130, :134, :155 | Critical. Events can be lost silently during the final. |
| 3 | §9 item 5 | Open whether refunds and the 90% minimum count per order or per car. | **Per order.** An order is on time only when every leg arrives by its deadline. The minimum counts won orders, and `onTimeShare`/`wonOrders` are per order.<br>One price is paid once, at the last delivery. Refunds are shares of the order price. The penalty is 2× the price; taking the whole order price as its base is an inference.<br>Still open: which leg sets the tier, how many lines are written, and how two different leg deadlines combine.<br>Per car: the failed visit, the premium fine and satisfaction. | RULES.md:146, :148, :30, :134-138, :165, :121, :140, :55; HANDBOOK.md:212; API.md:68-69 | High. One late leg makes the whole trade-in late. |
| 4 | §1.2 l41 | "Deadlines are 20:00 on business days." | True only for **option** deadlines; the last is 20:00 on the final Monday. A private delivery is due at the end of its booked hour + 30 min. A note's tighter deadline counts (reveal `noteDeadline`). Snow, or a car ready ≥1 day late, moves the deadline. | RULES.md:23, :45, :125, :53, :146; HANDBOOK.md:324, :328; API.md:103 | High |
| 5 | §9 item 2 | Requests carry a gearbox; `delivered`/`picked_up` carry the driver id. | `Car` is `{premium, electric, chargePercent}`, with no gearbox. The gearbox is known only from the note, a `visit_failed` with reason `licence`, or the reveal. `picked_up`/`delivered` are `{gigId, orderId, leg, placeId}`, with no driverId. Full shapes in §3 item 2. | openapi.json:1 (DeskEvent; PriceRequest.legs.car); types.py:90-94, :272-300 | High |
| 6 | §7 l363 | On 502/503/504: "wait 5 s, re-read state, continue". | A restart lasts up to a minute. Retry in a loop (the starter sleeps 5 s per try). Then resend and read state (snapshot + events) before acting. Before resending a post or offer, check it did not already apply. | API.md:157; starter.py:399-401; client.py:47-48 | High |
| 7 | M1 l197 | A 30–40-quote bulk burst "fits one batch". | It fits the 50-action cap. In the final, though, it costs N action tokens (bucket 50, refill 20/s). With fewer tokens the server refuses the whole request with 429 at once.<br>The kit usually waits client-side, but it can still get a 429 on a route's first call or with a second client on the same key. The wait is (N − remaining)/20 s: 40 quotes from an empty bucket wait 2 s of the 4.5 s window.<br>Reserve tokens for quotes, defer P2/P3 actions, or split the batch. | API.md:17, :129, :134; client.py:78-86, :139-140 | High |
| 8 | §1.5 l68; §2.8 l173; §2.9 l178 | A driver is notified when the pickup is within 30 km of home; that is the notified pool. | Distance is from the gig's **first** pickup, so stop order matters. Only drivers with notifications on are notified; the roster does not show who they are. Drivers are not notified where your gigs took them. A drop or no-show notifies again.<br>23:00–07:00 limits reading, not sending; whether a night notification is read at 07:00 or lost is unstated (test with `fork`).<br>A pool built from place lat/lon is an upper bound. It misses your drivers' endpoints and far drivers drawn by a high fee. | RULES.md:87; HANDBOOK.md:260, :233; types.py:397-404 | High |
| 9 | §1.2 l41 | "The next Monday is the last business day." | It is the last **deadline** day: a normal business day without requests. Business days are Mon–Fri, and only Sat/Sun are excluded. So Tue and Wed of the final week count toward the 50%/100% tiers. | RULES.md:22, :23, :146, :136-137; HANDBOOK.md:87, :90 | Medium |
| 10 | §1.4 l54 | A windowless stop uses the order window "cut to site hours". | It is cut to the site's **stated** hours, not real hours from a note, and runs to the order's deadline. At a dealer site it can end at the stated closing time on the deadline day, before 20:00, and that can expire the gig. | RULES.md:61; starter.py:130; HANDBOOK.md:325 | Medium |
| 11 | §1.4 l60 | The gig leaves the app after "the first stop window ends". | It leaves after the **earliest-ending** window of any stop; windowless stops count through their stated hours. The exception is the old-car slot in a trade-in, right after the new car's delivery. The gig then shows `withdrawn`. Repost it, and the windowless stops run to the world's end. | RULES.md:72, :69; HANDBOOK.md:207; starter.py:130 | Medium |
| 12 | §1.7 l84; §2.1 l134 | An EV without its stop "is 90 min late, fine €100"; fines are "worth 1–2 orders". | The fine always applies. The car arrives 90 min later than planned, which makes it late only if its slack is < 90 min. If the delay passes a site's stated closing time, the delivery counts at the next opening.<br>The cost can therefore exceed €100: a refund, a hit to the 90% gate, lower satisfaction, and halved L8 trust. The spec compares fines with revenue; measured against margin they cost many orders.<br>"Route" is undefined, and the starter sets `withCharging` on every EV < 30%. The premium fine has no stated side effect. | RULES.md:123, :124, :146, :55, :164; starter.py:256-257 | Medium |
| 13 | §1.3 l49 | Decline at ≥4× list "[verify no cap]". | The only cap is the schema's: integer cents, > 0, ≤ 9007199254740991. Fractions and values ≤ 0 get 400. There is no business cap.<br>No source says a quote far above list always loses. From L4 a won quote is a real order, and its refunds and the 2× penalty scale with the price.<br>"4×" is unsourced: set the multiple above the highest price a dealer accepts and confirm it never wins. | openapi.json:1 (Action.oneOf[0].prices); API.md:3; HANDBOOK.md:282, :109; RULES.md:47, :138, :154, :160, :164 | Medium |
| 14 | §1.3 l49 | "Always quote." | Only from level 4. At levels 1–3 every quote wins the first option at list price, so decline by sending no quote. | RULES.md:47, :154; HANDBOOK.md:104 | Medium (practice levels) |
| 15 | §2.1 l133 | About €75 per order. | €71,332/949 = €75.17 per won order, at the starter's list-price quoting. Revenue counts only on delivery: with about 12 orders undelivered, that is about €76 per delivered order if `revenueCents` is gross, which no source defines. At L8 the competitor is 1.26–1.54× list and trust adds up to +25%, so P will be higher, and every §2.2 cost scales with P. | HANDBOOK.md:57; RULES.md:51, :138, :160, :164; starter.py:106 | Medium |
| 16 | §2.4 l159 | `P_win = σ(−κ·ln(p/ĉ_eff) + v_option)` with an unindexed κ. | Use a per-dealer κ_d and v_{d,o}, as M7 already does: dealers differ in price sensitivity and in the value of speed. The form is a modelling choice. The sources say only that acceptance falls as price rises against the competitor, falls quickly above it, and that each option's price is compared with its speed value. Dealers ignore price at L1–3. | HANDBOOK.md:282; RULES.md:154 | Medium |
| 17 | §1.6 l77 | Hour words (FI, SV, EN) are the working hour 9–17. | RULES states this for Finnish and Swedish only; English is undetermined. Key on the language of the hour phrase, since notes can mix languages, and check English (especially "half three") against the reveal. | RULES.md:105; HANDBOOK.md:331; types.py:129 | Medium |
| 18 | §1.4 l57 | Reprice is allowed at any time; only withdraw needs the gig unbooked. | Reprice also needs an **unbooked** gig, and a booked driver keeps the booked fee. Ways to change it:<br>- Release the driver (25–100% fee, free after `driver_late`) and repost.<br>- After a drop or no_show the gig reopens and can be repriced.<br>Extra pay can still come on top: extra driving after a change of place, waiting, failed visits. | RULES.md:70, :74, :79, :110; HANDBOOK.md:187-188, :201, :205-206 | Medium |
| 19 | §2.8 l175 | A downward reprice makes overshoots fixable. | Only before a booking. Drivers book on a quick look at the app fee, and most views come in the first minutes, so an overshoot is usually booked first. Undoing it costs a 25–100% release fee plus a repost. A lower fee sends no notification. A booked ÷ first-viewed ratio < 1 enters driver beliefs, with an unstated effect. | RULES.md:70, :76, :79; HANDBOOK.md:201, :258, :266 | Medium |
| 20 | M11 l252 | Offers "fall back to the app". | An offer needs a posted `gigId`, and a posted gig is in the app and spends the order's notification. So the app runs **alongside** the offer, and an app booking turns a later yes into `expired`. | types.py:43-48; RULES.md:91, :97; HANDBOOK.md:198, :260 | Medium |
| 21 | §1.5 l71 | "A yes books at once." | A yes books only if the gig is still open and fits the driver's day; otherwise it comes back `expired` after 10 min. The first booking wins, from the app or another offer. Every offer sent counts toward 3 per driver per day, whatever the answer. | RULES.md:97, :91, :93; HANDBOOK.md:201 | Medium |
| 22 | §2.6 l167; M11 l252 | A relay offer at the driver's marginal cost will be taken. | A driver accepts when the fee pays for the gig "and what else their day is worth", and answers are noisy. Conditions:<br>- the driver must read the offer within its 10 min;<br>- the gig must fit the driver's day capacity;<br>- the gig must be posted and still open;<br>- the offer counts toward the limits.<br>Later-day gigs are planned from home, so relays help same-day pickups only. | RULES.md:96, :95, :83, :97, :93-94; HANDBOOK.md:278, :274 | Medium |
| 23 | §2.8 l174 | The opening fee matters most: post once, never ramp. | The premises hold, but the rule is [hyp]. Counterweights in the sources:<br>- a car no driver takes needs a higher fee in time;<br>- working drivers plan one more look;<br>- drivers expect only the rises they have seen;<br>- an unbooked order teaches nothing. | HANDBOOK.md:268, :258; RULES.md:11, :83 | Medium |
| 24 | §2.6 l165 | A reverse pair A→B→A has no deadhead and no ticket home. | It saves only the ticket home from B and the ticket out to B. The driver still travels to A and home from A, unless they live near A or their next pickup is there. Read the B→B road minutes from the map. Corridor pairs have real deadhead inside the 12 h. | HANDBOOK.md:223, :244; API.md:40; RULES.md:68, :83 | Medium |
| 25 | §1.5 l67 | Trip to the pickup, trip home. | The trip runs from where the driver is (home or the end of a previous gig) to home or the next gig. The ticket out is bought ahead and is cheap; the ticket home is bought on the day and is dearer. Transit time costs far less than time at the wheel. After a small town's last evening connection, the trip home is expensive. | RULES.md:83; HANDBOOK.md:244, :274 | Medium |
| 26 | M11 l252 | Candidates: drivers who viewed, booked or are finishing a gig. | A booking or a gig in progress proves the driver works today. Views are weak evidence, because non-working drivers browse the app too. A finishing driver may have no room left in their day, and their yes then comes back `expired`. | HANDBOOK.md:233, :352, :200, :258; RULES.md:83, :95, :97 | Medium |
| 27 | §1.9 l106 | Drivers = 26–40% × a random per-town factor. | The total stays at 26–40%, the same as L7. The factor redistributes each town's share; it does not cut the total. | RULES.md:160, :162; HANDBOOK.md:344 | Medium |
| 28 | §3 l187; M1 l195 | The ActionQueue runs at a flat 20 actions/s. | Final actions refill at 20/s but the bucket holds 50, so a burst of 50 is allowed. In practice a request costs 1 token whatever it carries. Final reads are a separate bucket (50/s, holds 50). The kit's Client already mirrors the buckets from the `RateLimit-*` headers. | API.md:128-130; client.py:65-86, :139-145 | Medium |
| 29 | §7 l362 (via M2 l202) | Verify no gap after reconnecting; check that `seq` is contiguous. | No source promises consecutive `seq`, only "a sequence number above `after`", oldest first and without repeats. Reconnecting with the last seq misses nothing. To double-check, use `GET /events?after=<last>`, and do not alarm on seq jumps. | API.md:111, :120, :19 | Medium |
| 30 | M2 l201 | Per-order P&L from the `ledger`. | `orderId`/`gigId` are nullable, and driver and release fees are per gig. You need a gig→orders map from the stops and a split rule for pooled gigs. Failed visits are per car. | types.py:324-325; RULES.md:79, :139, :140, :144; reveal_csv.py:69 | Medium |
| 31 | §1.10 l121 | Fewer requests helps more than parallelism. | Unsourced. Requests are bound by round-trip time: 1,250 requests × 20 ms ≥ 25 s, about 50 req/s per world. So parallel worlds help until the team's shared bucket binds (max 8 worlds). Fewer requests always helps. | HANDBOOK.md:118; API.md:30, :36, :132 | Medium |
| 32 | §1.2 l43 | `same_day` is offered if the request arrives by 15:00 and the car can arrive 2 h before the deadline. | The request must arrive by 15:00 **on the ready day**, and the deadline is 20:00 that day, so the car must be able to arrive by 18:00. Whether an earlier-day request can get `same_day` is ambiguous: check in data. | RULES.md:41; HANDBOOK.md:90 | Low |
| 33 | §2.6 l165 | Trade-ins are reverse pairs by construction. | The old car is collected at the new car's delivery place, in the same visit. Read both legs' places rather than assume the old car ends at the new car's pickup. The car can be rerouted, trade-ins cost drivers extra, and a trade-in over 12 h goes as two gigs. | RULES.md:30, :69, :110, :68; HANDBOOK.md:242 | Low |
| 34 | §2.9 l178 | Build the supply map once, at minute 0. | Refresh drop counts and experienced status during the week. No source says homes or licences change. Each read in the final costs a token, and the roster never shows who works. | API.md:20, :130; RULES.md:63; HANDBOOK.md:352 | Low |
| 35 | §1.9 l106 | `/drivers` gives per-town supply; read it at minute 0. | It gives pool size, home town, rating, licence, completed gigs and drops, but not who works on a day: that shows only through views, bookings and drops. Reading it at minute 0 is advice. | HANDBOOK.md:352; RULES.md:83, :162; API.md:20 | Low |
| 36 | §2.9 l178 | Reach empty-town pickups by offers. | An offer widens who hears of the gig, but the fee still pays the trip from where the driver is. It is cheap only for a driver near the pickup after a same-day gig, or one living near the delivery place. The offer limits apply. | HANDBOOK.md:278, :254, :274; RULES.md:83, :93-96 | Low |
| 37 | M11 l252-253 | Offers only 07:00–23:00. | An offer's 10 readable minutes must fall within 07:00–23:00, so stop sending at about 22:50. A night offer goes unread, comes back `expired`, and still counts toward 3 per day. Whether the world refuses night offers is unstated. | RULES.md:95, :97, :93 | Low |
| 38 | §1.11 l125 | A 10-min offer lasts 3 real s. | Only on a weekday 06:00–22:00. It lasts 1 s on Saturday, 1.5 s on the last Monday, and 0.5 s at night, on Sunday and after the last Monday. The quote window is always 4.5 s, because requests arrive only on weekdays 08–18. | API.md:120; HANDBOOK.md:141; RULES.md:20, :95 | Low |
| 39 | §2.8 l174 | Hold night wins until 07:00. | Orders are won at `respondBy`, so wins come at about 09:15–18:15. Night posts are reposts (after `gig_expired`, a release, `visit_failed`, or a withdrawn gig on cancellation), and a repost does not renotify drivers who already heard. A drop or no-show reopens the gig by itself. The rule matters only for first posts, such as pooled holds. | RULES.md:20, :35, :49, :75-76; HANDBOOK.md:205-206, :260 | Low |
| 40 | M1 l196-197 | Count 429s; expect about 0. | About 0 is right, but `Client.call` waits out 429s and token shortages inside the call, so a gateway built on it always reads 0. Wrap `_send` or read the headers, and time the token waits: they block the calling thread. | client.py:139-147; API.md:145 | Low |
| 41 | §1.4 l59 | Split a trade-in only above 12 h. | Above 12 h the split is **required**. Below 12 h one gig is advice: posted alone, the old car must be collected inside its slot. | RULES.md:68, :69; HANDBOOK.md:92 | Low |
| 42 | §1.10 l121 | An L8 starter week is about 1,891 requests. | That figure is one seed (spread-1). L6 weeks take 1,000–1,450, and a week takes about 95 s at 20/s during finals. The spec's own §10 already logs 2,490 requests in total. | API.md:28, :30; HANDBOOK.md:53 | Low |
| 43 | §1.9 l107 | Competitor price = list × factors. | The base is the list price **before** rounding to whole euros. | HANDBOOK.md:284 | Low |
| 44 | §1.9 l110 | Each on-time **order** wins satisfaction back. | Each on-time **car** does; a trade-in counts as 2 cars (inference). Each late or undelivered car lowers it. | RULES.md:55, :68; HANDBOOK.md:311 | Low |
| 45 | §1.6 l78 | Denied times do not count. | Denied **days** do not count either. | RULES.md:106 | Low |
| 46 | §1.1 l38 | `house-` teams (House starter, House best) play every round. | The docs say only that House best plays every round, and that house teams take no rank place. The live board on 13 Nov is an observation, not a rule:<br>- house-starter: 5/5 at every level;<br>- house-strong ("House best"): 5/5 at L2–8, 0 at L1;<br>- house-bahn and house-rookie: 0. | HANDBOOK.md:355; API.md:71 | Low |

---

## 2. [verify] items settled

| Spec ref | Marker | Answer | Source |
|---|---|---|---|
| §1.3 l49 (= §9 item 3) | `[verify no cap]` on the ≥4× list decline price | **Settled.** The only cap is the schema's: each price is an integer in cents, > 0 and ≤ 9007199254740991. A value ≤ 0 or a fraction fails the whole request with 400. There is no business cap, and no source guarantees that a high quote loses.<br>Rough ceiling (inference): competitor ≤ 1.54× list, × outage backup 1.3, × trust up to 1.25 ≈ 2.5× list, before lane and day factors. Pick a multiple well above that, and confirm in practice that it never wins.<br>At L1–3, send no quote. | openapi.json:1 (Action.oneOf[0].prices); API.md:3, :151; HANDBOOK.md:109, :282; RULES.md:47, :154, :160, :164 |
| §1.8 l103 (= §9 item 4) | `[verify]` how the hour tiers treat a Friday-due car delivered on Saturday | **Not settled by the docs.** The weekend exclusion is stated only for business-day lateness. Plain reading (inference), with clock minutes for the hour tiers and a car due Fri 20:00:<br>- Sat 10:00: 14 h late, 25%.<br>- After Sat 20:00, or on Mon or Tue: > 24 h and ≤ 2 business days late, 50%.<br>- Wed: 100%.<br>A car left at a stated-closed site counts at the next opening. Sites have short hours on Saturday, some are closed, and all are closed on Sunday, so the count can slide to Monday (50%).<br>Test: deliver a Friday-due car on Saturday in a practice world or fork, then read `late_refund` cents ÷ price. | RULES.md:146, :134-137, :124, :21, :19; API.md:105 |
| §6 l328 (= §9 item 7) | `[verify via client.board]`: a round stays playable until the next opens; each of its five worlds once | **Confirmed**, with the conditions listed in §3 item 7. | API.md:46-52, :66, :69-70 |

Spec l362 ("verify no gap") is prose, not a marker; correction row 29 answers it.

---

## 3. Open items (§9, l399-407) answered

### Item 1. Action JSON shapes: answered

Shapes come from `openapi.json:1` (`components.schemas.Action`, `Advance`, `Advanced`, `ActionResult`). The kit's `types.py:6-73` is looser: `StopRef` is `total=False` there.

```jsonc
// Every field is required unless marked "?". Action objects are not closed (no additionalProperties:false).
// <cents> = integer, 0 < x <= 9007199254740991 ; <min> = integer world minute, 0 <= x <= 9007199254740991 ; <id> = string, 1..64 chars

{"type": "quote",    "requestId": <id>,
                     "prices": {"same_day"?: <cents>, "next_day"?: <cents>, "within_3_days"?: <cents>}}
                     // schema has no minProperties, but RULES.md:47 requires at least 1 price

{"type": "post",     "stops":    [StopRef, StopRef, ...],                      // minItems 2, no max
                     "audience": {"experienced": <bool>, "manualLicence": <bool>},
                     "schedule": [FeeStep, ...]}                               // 1..48 items

{"type": "offer",    "gigId": <id>, "driverId": <id>, "feeCents": <cents>}

{"type": "reprice",  "gigId": <id>, "schedule": [FeeStep, ...]}               // 1..48 items

{"type": "withdraw", "gigId": <id>}

{"type": "release",  "gigId": <id>}

StopRef = {"orderId": <id>, "leg": 0 | 1, "kind": "pickup" | "delivery",
           "window"?: {"from": <min>, "to": <min>},                           // both required when window is present
           "withPlates"?: <bool>, "withCharging"?: <bool>}
FeeStep = {"at": <min>, "feeCents": <cents>}

// Transport
// POST /v1/worlds/{id}/actions   body: Action[] (1..50)   -> ActionResult[] in the same order
// POST /v1/worlds/{id}/advance   body: exactly one of (closed objects):
{"to": <int >= 0>,                              "actions"?: [Action, ...]}    // actions: 1..50
{"by": <int >= 1>,                              "actions"?: [Action, ...]}
{"untilEvent": [DeskEventKind, ...], "max": <int >= 0>, "actions"?: [Action, ...]}  // untilEvent: >= 1
//   -> Advanced (closed): {"results"?: [ActionResult, ...], "now": <int>, "events": [DeskEvent, ...]}
// ActionResult (closed): {"ok": true, "id": <id>}  |  {"ok": false, "reason": <string>}
```

Notes:
- **What 400 covers.** Not parsing fails the whole request with 400: a fraction, a value ≤ 0, `leg` 2, fewer than 2 stops, 0 or 49 steps, or an empty `actions` array. Leave the `actions` key out rather than send `[]`. (API.md:3, :151)
- **What `ok:false` covers.** An action that parses but cannot be done gets `{ok:false}` inside a 200. Reasons never depend on hidden facts. (API.md:158)
- **Result ids.** `ok:true` on a post returns the new gig's id (starter.py:205-206). The id for other actions is unstated.
- **No undo actions.** No action cancels an offer or withdraws a quote (HANDBOOK.md:180-189).
- **Fee order.** Non-decreasing fees within a schedule are a world rule, not a schema check (RULES.md:64).

### Item 2. Request and car fields; event payloads: answered

**Answer.** The request carries premium and EV charge level. It carries no gearbox field. `delivered` and `picked_up` carry no driver id.

**Gearbox, plates and tyres** are known only from:
- the note;
- `visit_failed`: `licence` means a manual gearbox, `no_plates` means plates are needed, and summer tyres show only as `not_ready`;
- the reveal's `LegTruth` (`manualGearbox`, `needsPlates`, `summerTyres`) after the week.

**Gig to driver:**
- `gig_booked`, and `offer_answered` with `answer == "accepted"` only, bind a driver to a gig.
- The snapshot's `Gig.driverId` holds the current driver.
- `driverPositions` covers only drivers working one of your gigs now.

Sources: openapi.json:1 (PriceRequest, Order, Gig, DeskEvent, LedgerLine, DriverProfile); types.py:90-135, :151-330, :359-404; HANDBOOK.md:211, :248; RULES.md:87, :144; API.md:100-102.

```jsonc
// Entities. Closed objects, every field required unless "?"; "|null" = nullable.
PriceRequest   {id, dealerId, batchId: string|null, arrivedAt: int, respondBy: int,
                legs: Leg[1..2], options: DeliveryOption[>=1], referenceFeeCents: int,
                note: {text: string, language: "fi"|"sv"|"en"} | null}
Leg            {car: Car, pickup: StopPlace, delivery: StopPlace}
Car            {premium: bool, electric: bool, chargePercent: int 0..100 | null}   // no gearbox, plates or tyres
StopPlace      {placeId, privateAddress: bool, window: {from: int, to: int}, hours: OpeningHours | null}
OpeningHours   {opens: int 0..1440, closes: int 0..1440, weekdays: int[>=1] (each 0..4),
                saturday: {opens: int, closes: int} | null}      // minutes of the day, Mon..Fri = 0..4: inferred from the bounds
DeliveryOption {kind: "same_day"|"next_day"|"within_3_days", deadline: int, listPriceCents: int}
Order          {id, dealerId, option, priceCents: int, deadline: int, legs: Leg[1..2],
                status: "waiting"|"booked"|"moving"|"delivered"|"cancelled",
                deliveredAt: (int|null)[] /* per leg */, lastPickupAt: int}      // no note, no referenceFeeCents; one deadline
Gig            {id, stops: StopRef[>=2], audience: {experienced, manualLicence}, schedule: FeeStep[1..48],
                status: "open"|"booked"|"working"|"done"|"withdrawn", postedAt: int, feeCents: int, driverId: string|null}
DriverPosition {driverId, placeId, gigId}
DriverProfile  {id, homePlaceId, rating: number 1..5, licence: "manual"|"automatic_only", completedGigs: int, drops: int}
LedgerLine     {at: int, kind: "revenue"|"late_refund"|"undelivered_penalty"|"driver_fee"|"failed_visit"|"release_fee"|"waiting"|"fine",
                cents: int (signed), orderId: string|null, gigId: string|null, detail: string}

// Events. Every event is {seq: int, at: int, kind, ...payload}. All payload fields are required.
price_request   {request: PriceRequest}
order_won       {order: Order}
order_lost      {requestId}
order_changed   {order: Order, message: {text, language}}          // message not nullable
order_cancelled {orderId, gigs: [{gigId, outcome: "withdrawn"|"released"|"shortened"|"continues"}]}
release         {orderId, leg: int}
gig_viewed      {gigId, driverId}                                   // no fee (seen fee only in reveal View.feeCents)
gig_booked      {gigId, driverId, feeCents: int}
gig_dropped     {gigId, driverId}
gig_started     {gigId, driverId}
driver_late     {gigId, driverId, pickupAt: int}
no_show         {gigId, driverId}
gig_expired     {gigId}
offer_answered  {gigId, driverId, answer: "accepted"|"declined"|"expired"}
picked_up       {gigId, orderId, leg: int, placeId}                 // no driverId
visit_failed    {gigId, orderId, leg: int, reason: "not_ready"|"closed"|"licence"|"no_plates"}   // no placeId
delivered       {gigId, orderId, leg: int, placeId}                 // no driverId; `at` = when the delivery counted (reader inference from HANDBOOK.md:212)
deadline_close  {orderId, lastPickupAt: int}
forecast        {text, from: int, to: int, placeIds: string[]}
ledger          {line: LedgerLine}
```

Also from the kit: the order id equals the request id, so keep every `PriceRequest` by id; `referenceFeeCents` covers the whole request (starter.py:109, :147).

### Item 3. Largest decline price: answered
See §2, row l49. The only cap is 9007199254740991 cents; there is no business cap.

### Item 4. Weekend hours in the hour tiers: not in the docs
See §2, row l103: a plain reading plus a ledger test.

### Item 5. Two-car orders: per order
See correction row 3. Still open: which leg sets the tier, how many refund or penalty lines are written, and how different leg deadlines combine.

### Item 6. When the 3-offers-per-day counter resets: not in the docs
- **Stated:** "At most three direct offers per driver per day" (RULES.md:93). Every offer sent counts, whatever its answer (ruling on §1.5 l71 and M11 l252-253).
- **Unstated:** the day boundary, whether a refused offer counts, and whether the limit is per team.
- **Working assumption:** day = ⌊minute / 1440⌋, since minutes run from Mon 00:00 (RULES.md:19).
- **Test:** send a 4th offer to one driver before and after 00:00, and read the `{ok:false, reason}`. Reasons never depend on hidden facts, so the reason should state the rule (API.md:158).
- **Related:** at most 3 open offers per gig (RULES.md:94).

### Item 7. Ranking-round window: confirmed, with conditions
- **No end time.** A round has no end time of its own. The organisers start each one, and `current`/`previous` show which round is live. (API.md:46, :61-66)
- **Unplayed worlds are lost.** When the next round starts, worlds not yet created in the old round are lost. A run created before the switch counts in its own round when it ends. (API.md:50)
- **Per level.** Five worlds per level, one unfinished run per level at a time (409 otherwise), and levels can run at the same time (API.md:47-48). `board:true` with a `seed` gets 400 (API.md:47).
- **When a team is ranked.** All five runs have ended and each meets the 90% minimum (API.md:69-70).
- **DELETE does not remove a run.** The run plays on to its end without you and counts. A ranking run uses a practice slot and cannot be forked or revealed. (API.md:51-52)
- **Throughput.** While a final runs, the practice limit is 20/s, so a level-8 week takes about 95 s (API.md:30, :128).
- **Timetable.** The spec's round timetable is in no source; API.md:46 gives only the example name "Saturday 15:00".

### Item 8. About 40 real notes from `study-1`: a task, not a doc question
- Notes act only from level 5, so collect them at level 5 or higher (API.md:107).
- Label them from the reveal's `LegTruth` and `noteDeadline` (API.md:100-103).
- `note.language` is `fi`, `sv` or `en`, and notes can mix languages (types.py:129; HANDBOOK.md:331).

### Item 9. House best's per-world numbers: a task, not a doc question
- The docs give only "ranked on all 20 at L7 and L8" on the organisers' 20 weeks (HANDBOOK.md:355).
- Per-run `marginCents`, `onTimeShare`, `wonOrders` and `ranked` are on the public board (API.md:63).
- The spec's status board (l17) says this is already pulled into `data/board/`.
- On the live board, House best's id is `house-strong` (observation, 13 Nov).

---

## 4. Omissions that change what the system should do (most impactful first; reader-found unless marked *ruled*)

1. **Note deadlines.** A tighter deadline in a note counts for on-time. No source says `Order.deadline` or `lastPickupAt` include it; `order_won` is stated to carry only the moved ready-day deadline. **Do:** the NoteReader sets its own deadline, and the system prices or declines on it. (HANDBOOK.md:324; API.md:103; RULES.md:146)
2. **When a delivery counts.** It counts at the driver's arrival, or at the site's next opening when the car is left at a stated-closed site. **Do:** plan deliveries inside the stated hours on the deadline day, not just before 20:00. (API.md:105; HANDBOOK.md:212; RULES.md:124)
3. **One bad action fails the batch.** An action that does not parse fails the whole request with 400, including the `advance` it rides on. **Do:** validate each action against the schema, send quotes in their own batch, and never send an empty `actions`. (API.md:151, :158; openapi.json:1 Advance)
4. **L8 list price and typical fee are a normal week's.** The list price wins most cars, and the typical fee often finds no driver. **Do:** do not anchor P on list or C on `referenceFeeCents`.
   - The accepted ceiling is about 1.6–1.9× list, or about 2.0–2.5× in an outage region, before lane and day factors (inference). So §2.4's 0.9–1.9× search can clip it.
   - (RULES.md:160, :164; HANDBOOK.md:349, :109)
5. **What `lastPickupAt` counts.** Road minutes, an EV's charging stop, and stated hours or a private slot. It leaves out plates, real hours from a note, note deadlines, drive-time variance and snow. When no pickup can be on time, it is the first minute the car can be collected. **Do:** keep your own margin. (RULES.md:77-78; HANDBOOK.md:225)
6. **`deadline_close` re-arms.** It comes again when the order loses its driver or when `lastPickupAt` moves later, with at most one pending; its payload carries `lastPickupAt`. A delivered leg also resets `lastPickupAt`, and no listed event carries the new value. **Do:** do not latch the warning, and re-read the snapshot after deliveries. (RULES.md:78; types.py:302-308)
7. **After `deadline_close`, only a higher fee or an offer helps,** and the warning fires whether or not the order is posted. **Do:** post pooled holds well before `lastPickupAt` − 3 h. (RULES.md:77)
8. **`post` and `offer` are not idempotent.** A resend makes a second gig or uses quota, and the kit auto-resends on reset connections. **Do:** check `snapshot.gigs` before reposting after `Unreachable`. (API.md:157; client.py:170-171)
9. **The SSE leaderboard is free.** `GET /v1/leaderboard` gives `status`, `now`, `endsAt`, `onTimeShare` and `ranked` at no token cost. The starter instead polls `GET /v1/final` every idle second, at a read token each. `Score` also carries `onTimeShare`, `undeliveredShare` and `ranked`, which the governor can read directly. (API.md:118, :134; starter.py:342; types.py:376-384)
10. **Stream behaviour.** Opened without `after`, the stream sends only new events. A stream more than 4 MB behind is closed with code 1013. **Do:** always open with `after=<last>` (−1 on a cold start) and keep handlers fast. (API.md:111)
11. **The snapshot is thin.** It holds only worldId, now, endsAt, openRequests, orders, gigs, driverPositions and score. It has no ledger, no past requests or notes, and no warning history. **Do:** persist every `PriceRequest`, and rebuild from events. (openapi.json:1 DeskSnapshot; starter.py:48-73)
12. **Only a drop or no-show notifies again.** Reposts after `gig_expired`, a release (including the free one after `driver_late`) or a withdraw do not. A repost at a higher fee counts as a raise, because the order keeps its first viewed fee. **Do:** after those events, use offers or a higher fee. (HANDBOOK.md:260, :268; RULES.md:79)
13. **Cancellation and change costs.** On `order_cancelled`:
    - `released`: you pay the release fee;
    - `continues`: you pay the full fee, and the car is not delivered;
    - `shortened`: the driver stays at the booked fee.
    A change of plan to a farther place adds pay for the extra driving, and `order_changed` reroutes even a started gig. (RULES.md:110, :115-117)
14. **`visit_failed` reasons reveal car facts.**
    - *ruled:* `licence` means a manual gearbox, and `no_plates` means plates are needed; summer tyres show only as `not_ready` (HANDBOOK.md:211; RULES.md:144; starter.py:156).
    - Reader only: a pickup at a closed site is a failed visit (RULES.md:144). In a multi-car gig the failed car loses its gig, so repost it alone (HANDBOOK.md:211).
15. **Snow.** A car on summer tyres gets its deadline moved by 1 day through `order_changed`, and it cannot be collected while snow falls there. Drivers kept home by snow drop that day's bookings. (HANDBOOK.md:328; RULES.md:83)
16. **Drivers plan by stated hours.** **Do:** when a note gives different real hours, set the stop windows yourself. (RULES.md:73)
17. **Most drivers know only the next day.** A gig for a later day reaches few drivers and ages in the app. **Do:** post `within_3_days` orders close to the pickup day. (RULES.md:83)
18. **Driver day types.** Day-job drivers are free only in the evening, weekend drivers work only on Saturday, and each driver has a longest gig they accept. **Do:** make λ and fees depend on hour and weekday. (HANDBOOK.md:233)
19. **Chains form on their own.** For a driver who already has one of your gigs, a second costs only the extra time and tickets. **Do:** count your drivers' endpoints as supply. (HANDBOOK.md:244; RULES.md:87)
20. **Level gates.** Notes act from L5, offers and multi-car gigs from L3, learning and drops from L2. **Do:** test the NoteReader at L5+, pooling and offers at L3+. (API.md:107; RULES.md:154)
21. **`withCharging` rule.** It is needed only for an EV under 30% charge on a route over 200 km; the starter sets it for every EV under 30%. An unneeded flag adds 40 min and driver cost. (RULES.md:123; starter.py:256; HANDBOOK.md:242)
22. **The audience is per gig,** so pooling a premium car makes the whole gig experienced-only. Untested: whether an "everyone" gig taken by an experienced driver avoids the fine. (types.py:36-41; starter.py:160; RULES.md:121)
23. **Request windows.** Before a win, a pickup window starts at the stated ready time, and dealer-site windows end at the latest option's deadline. **Do:** cost each option on its own deadline. (RULES.md:31)
24. **`next_day` deadline.** It is the next business day after the ready day, so a car ready on Friday is due Monday. (RULES.md:42)
25. **Private seller slots** are sized for a driver booked at the win, with the 3-hour warning to spare. **Do:** post private pickups at once. (RULES.md:31)
26. **`release` also fires** for a car held until it was ready. **Do:** use it as the trigger to post. (HANDBOOK.md:209)
27. **In the final, a request not answered in time goes to the competitor,** and unquoted requests cost goodwill. **Do:** send a fast default quote before refining. (RULES.md:158, :55)
28. **Ranking-run pitfalls.** `board:true` with a `seed` gets 400. A run uses a practice slot. The starter's delete-on-error still leaves the run counting. (API.md:47-52; starter.py:406-416)
29. **Ranked first, margin second.** House teams take no rank place, and when fewer than 10 teams are ranked, only ranked teams present. (API.md:71, :118; RULES.md:15)
30. **Trust still meets the competitor.** The dealer still compares your price with the competitor's, and the competitor lowers its prices where you win most. (RULES.md:165; HANDBOOK.md:294)
31. **Revenue lags.** Revenue, and with it the trust credit counted from the ledger, is booked at the order's last delivery. (HANDBOOK.md:212)
32. **Ledger kinds.** The kinds are fixed. `late_refund` ÷ price gives the tier applied, which settles the l103 question empirically. (types.py:322)
33. **Competitor moves.** Its place steps and weekly reshape do not change prices on average. Outages are likelier in busy regions. (HANDBOOK.md:293, :109)
34. **`batchId`** is nullable and explained nowhere, and requests often arrive together. Check whether it marks bulk orders. (types.py:135; RULES.md:7)
35. **Driver beliefs** are per driver, a running mean that fades. A driver who never viewed your gigs keeps a new driver's belief. (HANDBOOK.md:266)
36. **Offer views.** Opening an offer emits `gig_viewed`. Whether the offer's fee can become the "first viewed fee" is unknown: check `views.csv` in the reveal. (HANDBOOK.md:200)
37. **Late drivers and reopened gigs.** `driver_late` carries `pickupAt`. A reopened gig keeps its old schedule: reprice it if stale. (RULES.md:74; HANDBOOK.md:206)
38. **No-shows in the roster.** The roster does not count a no-show as a drop. **Do:** track no-shows from events. (RULES.md:75)
39. **Small towns** have a last evening connection, after which the trip home is expensive. **Do:** pay more for evening deliveries there. (HANDBOOK.md:244)
40. **Drop timing.** Drivers book on a quick look and plan by the next morning. An evening booking for the next day is not safe until morning. (HANDBOOK.md:272)
41. **Practice limits and forks.** An over-limit practice request waits up to 1 s before a 429. The first `advance` on a fork returns the whole history. **Do:** key event logs by worldId. (API.md:134, :34)
42. **`GET /v1/worlds`** lists `kind`, `boardRun` and `ended`, which shows ended test finals and stuck slots. (API.md:13)
43. **Opening hours.** They have a weekdays list (0–4, at least one) and a nullable Saturday; private addresses have null hours. (types.py:101-113)
44. **How drivers read offers.** Through a notification or by opening the app while the offer is open. Working drivers read most offers in their free hours, and answers are noisy. **Do:** model acceptance as a probability. (RULES.md:95; HANDBOOK.md:278)

Left out because the skeptic struck them: "ratings change"; "a timed-out request may still have been applied"; "drops and no-shows need a repost".

---

## 5. Rejected corrections (reader said wrong, skeptic kept the spec)

- **§1.10 l114** (`reveal` "403 on ranking runs"): the spec is right. Additions: a practice world gives 409 before its end, and the final gives 403 until it ends. (API.md:23, :51, :120)
- **M1 l195** ("retries after 5 s … with a state rebuild"): this matches the starter's retry loop. Retry until the server answers, which takes under a minute; see row 6. (HANDBOOK.md:178; starter.py:399-401; API.md:157)
- **M2 l203** (restart invariance on a fixed seed): this holds on practice worlds, which stand still. It requires LLM outputs to be cached and decisions to be pure functions of state. (API.md:32; RULES.md:152)

---

## 6. Counts

| Slice | Claims | Confirmed | Partly: upheld | Partly: rejected | Not in docs |
|---|---|---|---|---|---|
| score-account-l8 | 62 | 51 | 7 | 0 | 4 |
| week-quotes-notes | 47 | 34 | 8 | 0 | 5 |
| gigs-cars | 42 | 36 | 5 | 0 | 1 |
| drivers-offers | 56 | 37 | 16 | 0 | 3 |
| api-limits-clock | 72 | 56 | 12 | 3 | 1 |
| open-items | 7 | 3 | 2 | 0 | 2 |
| **Total** | **286** | **217** | **50** | **3** | **16** |

- **Claims checked: 286.**
- **Confirmed: 220.** That is 217 confirmed by the reader plus the 3 the skeptic reinstated.
- **Corrected: 50.** No claim was marked "contradicted", and no ruling was missing.
- **Not in docs: 16.** These include "registration closes at 07:30", "~1,000 requests/week", "30 towns", "≥4× list", "0.9–1.9× search range", "×1.05 offer fee", the offer-counter reset and "seq contiguous".
- **Overlap:** the §9 items 3, 4 and 7 rows repeat the three `[verify]` claims (l49, l103, l328).
