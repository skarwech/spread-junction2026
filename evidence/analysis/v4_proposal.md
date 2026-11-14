# v4 desk policy for level 8: proposal

14 Nov 2026. Every number below is printed by `evidence/analysis/v4_proposal.py`, and the printout is saved as `evidence/analysis/v4_proposal_out.txt`. "Px" refers to a section of that printout. Figures marked "risk.md Sx" come from the risk analysis and its own printout, `risk_out.txt`.

To reproduce (about 2 minutes, no network, no worlds created):

    .venv/bin/python -m evidence.analysis.v4_proposal > evidence/analysis/v4_proposal_out.txt

The script reads the 64 pinned level-8 runs of `governor_parse.RUNS`. That list holds one run per identical setting on dev-1 to dev-4 and hold-1 to hold-6, excludes `wc721c95a136b417e5d7c`, and contains only runs with a `summary.json`. It also reads the sweep files.

## 0. Read this first: what the proposal rests on

- **One of the three analyses arrived, and it is unchecked.** The task promised three checked analyses. It supplied one, `risk` (risk.md), with `check: null`.
  - A review of risk.md is under way (`risk_review_data.py`, last changed 10:47), but no review report exists.
  - No governor analysis and no fee analysis exist on disk. There are only the data layers `governor_parse.py` and `governor_data.py`.
- **I derived the governor, price and fee evidence myself, and nobody has checked it.** It is in `v4_proposal.py` and `v4_data.py`.
- **Evidence tags.** Every parameter below carries one of these tags:

| Tag | Meaning |
|---|---|
| **PLAYED** | A real practice week played this setting. |
| **REPLAY** | Offline recount of played weeks; it cannot show the drivers that a decline frees. |
| **DERIVED** | Computed here from played weeks, but never played as a rule. |
| **RULES** | Follows from the text of RULES.md. |
| **NONE** | No evidence. |

- **How the parts are judged.** An unranked week scores nothing. Each part is judged first by the number of weeks at or above 0.90 on time, then by the worst week, then by margin.

## 1. The current best, and what v4 must fix

**Current best (v3)** is the policy actually played: `priced price_mult=1.5 fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5`. Its server results (P1):

| Setting | Total margin € | Weeks ≥ 0.90 | Worst week | Margin of ranked weeks € |
|---|---|---|---|---|
| 1.5x, deadline fees, no filter | −4,421 | 3 of 10 | 0.624 | 16,051 |
| … slack ≥ 4 h, drive ≤ 5 h | 59,342 | 7 of 10 | 0.763 | 40,518 |
| **… slack ≥ 6 h, drive ≤ 5 h (v3)** | **59,037** | **8 of 10** | **0.867** | **46,289** |

- risk.md quotes €60,490 for v3. That is a sum over orders, not the server's margin. This parser's per-order sum is €60,565 (P8).
- **The failures.** v3 misses the gate on hold-2 (0.890, 427 orders) and hold-5 (0.867, 278 orders), while dev-1 and hold-1 pass with 364 and 365 orders (P1).
  - So no fixed weekly volume cap fits every world. The governor must read the world as the week goes on.
- **Weeks fall into two groups by v3's on-time share** (P1). The two signals the governor reads online (Part 2) sort the weeks the same way (P3, P5):

| Group | Weeks | v3 on-time | Win rate at 1.5x, no filter | Most warnings in any 24 h, v3 |
|---|---|---|---|---|
| Stressed | dev-1, dev-3, hold-1, hold-2, hold-5 | 0.867–0.948 | 0.34–0.57 | 19–46 |
| Healthy | dev-2, dev-4, hold-3, hold-4, hold-6 | 0.968–1.000 | 0.14–0.32 | 0–5 |

## 2. The proposal: four parts

```
quote(request):                                    # dealer's first option only
    if slack < 6 h or drive > 5 h:  quote 4 x list                 # Part 3: risk filter
    m = 1.8 if warnings_24h >= 10 else ladder_m                    # Part 2: governor
    quote round(list x m x (1 + 0.01 x trust[dealer]))             # Part 1: price
ladder_m in {1.50, 1.65, 1.80}: one rung up when the win rate of the last 40 answered quotes is >= 0.40,
    one rung down when it is < 0.15; the window restarts after each step     # Part 2
gigs: open at the typical fee, rise in 6 steps to 2x by lastPickupAt - 2 h; after deadline_close,
    the starter's steep schedule (1.5x to 2.5x)                              # Part 4: fees, unchanged
```

### Part 1. Price: 1.5 × list, plus 1% for each order delivered on time to that dealer

**Rule.** Quote round(list price of the dealer's first option × m × (1 + 0.01 × n_d)).
- m comes from Part 2, and its floor is 1.5.
- n_d is the dealer's on-time count, kept from our own ledger as RULES.md:163-165 defines it. A revenue line with no late refund adds 1, up to 25. A revenue line with a late refund halves the count, rounded down. The count starts at 0.

**Why.**
- **Base 1.5.** It is the only multiplier ever played with the filter. Without the filter, 1.5 beat 1.35 on all 4 dev seeds, and beat 1.65 on only 2 of 4 (P2). Part 2 handles the seeds where 1.65 wins.
- **Trust markup.** The rules say a dealer accepts prices 1% higher for each counted order. A markup of exactly 1% per count should therefore leave our chance of winning unchanged, and turn trust into margin.
  - **Today we spend trust on volume.** At a fixed 1.5x, the win rate rises with the dealer's count: from 0.80 of the run-day mean at count 0 to 1.39 at count 11 or more (P4). In a shortage, volume is the wrong use for it.
  - **Our trust stock is large.** The won orders of the v3 weeks arrived with mean counts of 5.9–12.0, or 6.2–11.3% price-weighted.
    - The count passes a check against the ledger: in every week, the halvings match the delivered late orders to within one, for example 47 of 47 in hold-2 (P4).
  - **Value.** If wins stayed the same, the markup would have added €1.1k–3.8k per week, €22,413 over the 10 v3 weeks, against €59,037 of margin (P4).
  - **Concentration.** One dealer holds 27–60% of our won orders in each week, so most of the value sits with that dealer (P4).
- **`options=first` and `decline_mult=4`, unchanged.** Over the 64 runs, 6,666 declines at 3× list or more won no order (P7).

| Parameter | Value | Tag | Evidence |
|---|---|---|---|
| `price_mult` (ladder floor) | 1.5 | PLAYED | P1, P2 |
| `trust_markup` (new) | 0.01 | RULES + DERIVED | RULES.md:163-165; P4. **Never played.** |
| `options` | first | PLAYED | All runs. `all` was never played. |
| `decline_mult` | 4 | PLAYED | P7: 0 wins out of 6,666 declines |

### Part 2. Governor: a three-rung price ladder read from two signals

**Rule.**
- **Rungs.** m is 1.50, 1.65 or 1.80 (`ladder_step=0.15`).
- **Signal A, market level.** Take the win rate of the last 40 answered quotes that were not declines. If it is 0.40 or more, move one rung up. If it is below 0.15, move one rung down, never below 1.5. After each step, the window restarts.
- **Signal B, capacity brake.** While our orders have drawn 10 or more `deadline_close` warnings in the trailing 24 hours, quote at the top rung, whatever signal A says.
- Part 1's trust markup applies on top of every rung.

**Why one actuator.** At level 8, a dear competitor and a driver shortage come together: the competitor "pays its own drivers more, so its price level is higher" (RULES.md, shortage). So a high win rate tells us two things at once:
- we can charge more;
- we are winning more cars than the drivers can move.

Raising the price answers both.

**Evidence for signal A** (DERIVED from played weeks; the switching rule was never played):
- **The win rate ranks the weeks.** The weekly win rate at 1.5x, unfiltered, has a Spearman correlation of −0.85 with v3's on-time share and +0.84 with its most warnings in 24 h (P3). The 5 weeks with a win rate of 0.34 or more (0.34–0.57) are exactly the 5 stressed weeks. The healthy weeks lie at 0.14–0.32.
- **The best multiplier follows the win rate.** On each dev seed, the best fixed multiplier tested won 14–30% of quoted requests (P2).
  - dev-1 and dev-3 win 0.43 at 1.5x. There, 1.65 beats 1.5 by €5,050 and €6,271.
  - dev-2 and dev-4 win 0.14 and 0.20 at 1.5x. There, 1.5 beats 1.65 by €2,057 and €2,334.
  - Reading the win rate picks the better multiplier on all 4 seeds.
- **Day by day it flags the right weeks early** (P3). On the v3 weeks, the daily win rate is 0.40 or more:
  - in the stressed weeks on 3–4 days, starting Mon (dev-3, hold-1), Tue (hold-2, and hold-5, where it lands exactly on 0.40) or Wed (dev-1);
  - in the healthy weeks on 0–2 days, mostly Friday, when trust has built up, which Part 1's markup absorbs.
- **The price-war day.** Each week's lowest daily win rate is 0.01–0.21, which is consistent with the price war. In dev-2 and hold-3 that day hardly stands out. On such a day the ladder falls to its floor.
- **The floor stays at 1.5,** because 1.35 earned less than 1.5 on all 4 seeds (P2).
- **Window size.** 40 answers is 2.4–2.8 hours of quoting (P3).
- **Thresholds.**
  - **0.40.** The ladder sees the win rate on the quotes the filter lets through. On the v3 weeks that weekly rate is 0.40–0.62 in the stressed weeks and 0.16–0.36 in the healthy ones (P3), so 0.40 sits on the split.
    - hold-5 sits exactly on the threshold, not above it, so whether the ladder catches hold-5 is a coin toss.
    - The standard error of a 40-answer rate is about 0.075, so single windows will cross 0.40 in healthy weeks too.
  - 0.15 is where the cheap seeds' best multiplier sat (0.14 and 0.20). At 1.65 those seeds won 0.06–0.07 and lost money.

**Evidence for signal B** (DERIVED; it cannot be replayed):
- **It fires only in the stressed weeks.** At 10 warnings the brake fires in all 5 weeks whose v3 on-time was 0.948 or lower, and in none of the 5 at 0.968 or higher. Those peak at 0–5 warnings, against 19–46 (P5). In those 5 healthy weeks it would have cost nothing.
- **Warnings predict lateness.** Over all 1.5x runs with deadline fees, orders that arrived after 10–19 warnings in the previous 24 hours were late 19.5% of the time, and after 20 or more, 31.6%. With no warnings, 4.2% (P5).
- **Why the top rung and not a decline.** dev-1 at 1.8x was the best dev-1 run of the sweep: €6,772 at 0.911 on time, with 146 orders. That run used starter fees and no filter (P2).

**What signal B cannot do.**
- **It fires late:** from Wed 20:55 (hold-2) to Fri 10:01 (hold-1) (P5).
- **It cannot rescue hold-5 alone.** 26 of hold-5's 37 late orders arrived before it fires. Signal A flags hold-5 on Tuesday.
- **Replay shows no gain.** A state-blind replay that declines while the brake is on gives 8 of 10 weeks and a worst week of 0.857 (P5). That is a floor, not a forecast: the replay keeps every other order's outcome and cannot free a driver.

| Parameter | Value | Tag | Evidence |
|---|---|---|---|
| `ladder_step` (new) | 0.15 | PLAYED grid | Only 1.5, 1.65 and 1.8 were played (P2); 1.8 only on dev-1 and dev-2, with starter fees |
| `ladder_up` (new) | 0.40 | DERIVED | P3. Chosen on the same 10 weeks |
| `ladder_down` (new) | 0.15 | DERIVED | P2. Chosen on the same 4 dev weeks |
| `ladder_n` (new) | 40 | DERIVED | P3: about 2.5 hours of quotes |
| `brake_dc` (new) | 10 | DERIVED | P5. Chosen on the same 10 weeks |

### Part 3. Risk filter: decline when slack is under 6 h or the drive is over 5 h (unchanged)

**Rule.** Quote 4 × list (a decline) when the deadline minus max(ready time, respondBy) minus the road minutes is less than 6 h, or the drive is longer than 5 h. This is `desk.policy.risk`.

**Why.**
- **It is the only selection rule with played evidence:** 8 of 10 weeks against 7 of 10 at 4 h of slack (P1).
- **The challenger.** risk.md's model F would decline at P(late) > 0.10. On the same pessimistic basis it beats the filter:

| Rule | Basis | Margin € | Weeks ≥ 0.90 | Worst week | Source |
|---|---|---|---|---|---|
| Model F, decline at P(late) > 0.10 | REPLAY | 45,750 | 7 of 10 | 0.837 | risk.md S10d |
| Filter | REPLAY | 40,484 | 6 of 10 | 0.767 | risk.md S10d |
| Filter | **PLAYED** | — | **8 of 10** | — | P1 |

- **Why model F is not adopted yet:**
  - It has never been played.
  - Its threshold was chosen with the hold seeds in view.
  - It has ten coefficients.
  - Its analysis has not been checked.
  
  So it stays an arm in the sweep below, not the default.

| Parameter | Value | Tag | Evidence |
|---|---|---|---|
| `min_slack_h` | 6 | PLAYED | P1 |
| `max_drive_h` | 5 | PLAYED | P1 |
| `max_p_late` (risk.md's new parameter) | off (1.01) in v4 | REPLAY | Challenger arm F |

### Part 4. Fees: the deadline schedule (unchanged)

**Rule.** Post at the typical fee. Rise in 6 even steps to 2× by lastPickupAt − 2 h. After `deadline_close`, use the starter's steep schedule: 1.5× at once, plus 0.25× every 30 minutes, up to 2.5×.

**Why.**
- **Deadline fees beat starter fees on margin in 11 of 12 paired weeks:** mean +€1,379, median +€1,121. On on-time share they win only 6 of 12 (P6).
- **Fees are the largest cost.** Driver and release fees are 67–81% of revenue in the v3 weeks (P6).
- **The opening fee sets most of what we pay:**
  - 64–90% of bookings are at the schedule's opening fee;
  - 0–13% come under the steep schedule after the warning;
  - the median booked fee is 1.00× the typical fee.
- **What makes v3 orders late:** "booked after lastPickupAt" is the cause of 104 of the 184 late orders (P6).

These facts point to two follow-up arms, a lower `fee_open` and a larger `fee_lead_h`. They are not evidence for any value, so v4 leaves the fees alone.

| Parameter | Value | Tag | Evidence |
|---|---|---|---|
| `fee_mode` | deadline | PLAYED | P6: 11 of 12 pairs |
| `fee_open` | 1.0 | PLAYED, never varied | P6 |
| `fee_cap` | 2.0 | PLAYED, never varied | |
| `fee_lead_h` | 2 | PLAYED, never varied | |
| `fee_steps` | 6 | PLAYED, never varied | |

## 3. New parameters (to add to `desk.policy.Params`; `Params.parse` rejects unknown keys)

| Name | Type, default (off) | Meaning |
|---|---|---|
| `trust_markup` | float, 0.0 | Multiply each quote by (1 + trust_markup × n_d). n_d is the dealer's on-time count from our ledger: +1 at a revenue line with no late refund, capped at 25; halved, rounded down, at a revenue line with a late refund; starting at 0. |
| `ladder_step` | float, 0.15 | Distance between rungs. The rungs are price_mult + {0, 1, 2} × ladder_step. |
| `ladder_up` | float, 999 (off) | Move up one rung when the win rate over the last `ladder_n` answered, non-declined quotes is ≥ ladder_up. |
| `ladder_down` | float, −1 (off) | Move down one rung when that rate is < ladder_down. Never below price_mult. |
| `ladder_n` | float (a count), 40 | Window size. It restarts after every step, and no step happens until it is full. |
| `brake_dc` | float, 999 (off) | While at least brake_dc `deadline_close` events for our orders fall in the trailing 1,440 minutes, quote at the top rung (price_mult + 2 × ladder_step). |
| `max_p_late` | float, 1.01 (off) | risk.md: decline when model F's P(late) exceeds it. It replaces `min_slack_h` and `max_drive_h` in arm F. |

## 4. Sweep: six settings against the current best

Each arm changes one thing from arm A, except arm E, which is v4 complete.

```
priced price_mult=1.5 fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5
priced price_mult=1.5 fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5 trust_markup=0.01
priced price_mult=1.5 fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5 ladder_step=0.15 ladder_up=0.40 ladder_down=0.15 ladder_n=40
priced price_mult=1.5 fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5 ladder_step=0.15 brake_dc=10
priced price_mult=1.5 fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5 trust_markup=0.01 ladder_step=0.15 ladder_up=0.40 ladder_down=0.15 ladder_n=40 brake_dc=10
priced price_mult=1.5 fee_mode=deadline fee_open=1.0 fee_cap=2.0 fee_lead_h=2 max_p_late=0.10
```

| Arm | Tests |
|---|---|
| A | Current best (v3) |
| B | Part 1 trust markup alone |
| C | Part 2 signal A alone |
| D | Part 2 signal B alone |
| **E** | **v4 complete** |
| F | risk.md's model rule in place of the filter |

**Seeds.**
- Use 8 fresh level-8 seeds, for example `v4-1` to `v4-8`. Every dev and hold seed has informed a threshold here or in risk.md.
- hold-2 and hold-5 can be added as a regression check only.
- 6 settings × 8 seeds is 48 runs.

**Decision rule.** Adopt E, or any single arm, over A only if all three hold on the fresh seeds:
1. it passes at least as many weeks;
2. its worst week is no more than 0.01 lower;
3. its total margin is higher.

With 8 weeks, a difference of one passed week is within noise.

**Next fee arms,** after this sweep and from the winner: `fee_open=0.85` and `fee_lead_h=4`.

## 5. What the data does not support

1. **The trust markup has never been played.** Its value rests on the rules' wording: accepted prices rise by 1% per count. The €22,413 is an upper bound that assumes identical wins and no answer from the competitor, which "lowers its prices for that dealer" where we win most (HANDBOOK). The win-rate gradient in P4 is confounded by dealer identity.
2. **No switching rule has ever been played.** Neither the ladder nor the brake was played. Their thresholds (0.40, 0.15, 40, 10) were chosen on the same 10 weeks that motivate them. Multipliers of 1.65 and 1.8 were never played with the filter, and 1.8 only on two seeds, with starter fees.
   - `ladder_up=0.40` was set on win rates measured without the trust markup. With the markup (arm E), rates late in the week will be lower, so the ladder may fire less than P3 suggests.
3. **No replay can measure a governor.** Its effect is the drivers it frees. A state-blind replay shows no gain (P5), and a played filter beat its own replay by 1.9 points of on-time share on average (risk.md S10b).
4. **The brake alone does not rescue hold-5:** 26 of its 37 late orders arrived before the brake would fire (P5). Whether the ladder rescues hold-5 or hold-2 is unknown.
5. **Model F has replay evidence only, and its analysis is unchecked.** risk.md's own caveats apply: one desk's logistics, note deadlines not parsed, and the trust cost not modelled.
6. **Fee values are untested.** Only `fee_open=1.0 fee_cap=2.0 fee_lead_h=2 fee_steps=6` was played. Nothing here supports a different value, or rules one out.
7. **Ten weeks is a small sample.** v3 passed 8 of 10. That does not mean an 80% chance of ranking in the final: the interval around 8 of 10 is wide.
8. **Missing analyses.** Two of the three promised analyses (governor, fees) do not exist. The third has no independent check.
