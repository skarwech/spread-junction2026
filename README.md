# Spread dispatch desk (Junction 2026, Bahn challenge)

A system that does a dispatcher's job for one simulated week: it quotes car dealers, posts gigs for freelance
drivers, and keeps at least 90% of won orders on time. Built step by step, each step with its own evidence page.

## Results

| Run | Performance | Margin |
|---|---|---|
| Kit starter (reference week `spread-1`) | 0/1 | −€72,612.51 |
| Step 8 policy, 16 fresh L8 weeks | **16/16 ranked**, worst 93.2% on time | **+€143,934** (+€8,996 a week) |
| Final fee cap 1.85× vs 2× control, 16 new paired weeks | **16/16 ranked**; worst 92.4% vs 93.0% on time | **+€148,177 vs +€140,585** (+€475/week) |
| Follow-up slack limit, 7 h vs 8 h, 16 fresh paired L8 weeks | **16/16 vs 15/16 ranked**; worst 92.62% vs 88.93% on time | **+€169,285 vs +€165,592** (+€231/week) |
| Test final 3, Sun 01:00 (`f88a11d932a63ddb3f413`) | **36th**, ranked; 94.42% on time; 251 won orders; 0 undelivered | **+€5,912.57** |
| Previous policy, same original 16 weeks | 16/16 ranked, worst 90.6% on time | +€123,805 |
| Test final 2 (before step 8) | ranked, 97.5% on time; 62nd of 75 ranked teams | +€7,796.59 |
| Prior live rehearsal (fee cap 2×, 2 runs with SIGKILL) | 1,015/1,015 requests quoted in time; 96.9% on time | +€16,428 |

## Season 10: same-week L8 comparison

The **€102,581.93** result is Juhus's total across five ranked L8 weeks. We then ran our policy on those same
five weeks: **€50,220.00**, rank **52**, all five ranked. This is a paired comparison on identical worlds,
not a single-week score compared with a five-week total. Juhus won 2,367 orders (473/week) at 97.30% on time;
we won 1,574 (315/week) at 96.44%. Margin per order was €43.34 for Juhus and €31.89 for us. The gap comes
mainly from order volume and margin per order, not from the ranking threshold. See the [five-week result
artifact](evidence/ranking_current/season10.json) and [public leaderboard snapshot](evidence/l8_season10_top.json).

Test final 3 gives a same-world comparison: first place earned €14,111.66 on 445 orders (95.96% on time); we
earned €5,912.57 on 251 orders (94.42%). We attached at world minute 1205, after 212 requests had closed;
all 824 requests we saw were quoted quickly. Startup cost us market coverage, but order volume and margin
per order also lagged, so fixing startup alone would not close the whole gap. See
[the test final 3 results snapshot](evidence/final_leaderboard.json).

## Season 10 results across all levels

We ran the same L8 launch policy on the five ranked weeks at every level. It ranked all 35 weeks at L2–L8.
L1 overloaded badly: 980 orders won in its first week, only 79 delivered, and 901 undelivered, so all five
L1 weeks failed the ranking gate. Follow-up inspection found a bug as well as a tuning issue: the L8 six-step
fee schedule was rejected at L1, which allows only one step (1,021 of 1,106 attempted posts were refused in
the first week). Also, at L1–L3 a high-price “decline” still wins because dealers ignore price; declines must
send no quote. The desk and the all-level runner now handle both rules.

| Level | Board rank | Five-week margin | On time | Won orders |
|---:|---:|---:|---:|---:|
| 8 | 52 | €50,220.00 | 96.44% | 1,574 |
| 7 | 14 | €33,376.26 | 96.58% | 1,608 |
| 6 | 15 | €18,045.32 | 99.28% | 978 |
| 5 | 3 | €15,167.43 | 98.56% | 969 |
| 4 | 3 | €14,441.82 | 99.62% | 796 |
| 3 | 2 | −€9,290.67 | 93.35% | 4,931 |
| 2 | 2 | €2,756.22 | 94.33% | 4,954 |
| 1 | unranked | −€730,582.88 | 1.48% | 4,925 |

### Low-level follow-up (practice only)

We fixed the L1 fee schedule to send one step and changed L1–L3 declines to send no quote. On L1, a paired
capacity sweep showed that a hard outstanding-order cap lowered margin. We then tuned the one-step driver fee
and route filters, selecting a cautious candidate of `fee_open=0.85`, `max_drive_h=4`, `min_slack_h=7`, with
no cap. Four fresh holdout weeks averaged **€5,754 margin and 97.23% on time**; the worst on-time result was
94.17%. The same four weeks at the 0.9× fee averaged €5,017 and 98.02% on time. This is a practice result,
not a new board score.

After the no-quote fix, four practice weeks at L2 averaged €3,448 and 97.7% on time; four at L3 averaged
€3,971 and 97.4% on time. The all-level ranking runner now uses the L1-specific profile and the existing
L8 profile at other levels. Evidence: [L1 capacity sweep](evidence/sweeps/l1_capacity_v1.json), [L1 fee and
risk sweep](evidence/sweeps/l1_margin_v2.json), [L1 holdout](evidence/sweeps/l1_holdout_v3.json), [L2](evidence/sweeps/l2_decline_v1.json), and [L3](evidence/sweeps/l3_decline_v1.json).

## The ideas

1. **Price to the week**: quote above list; an adaptive multiplier steers toward 40% of real quotes won,
   never below the typical fee × 1.15, and rises when intake is high (`desk/policy.py`, `Learning`).
2. **Fees to the deadline**: open at 0.9× the typical fee and rise to 1.85× by the last pickup time − 2 h;
   fee increases pause overnight from 22:00 to 07:00.
3. **Quote a safe slower option**: test final 3 used at least 8 h of slack and no more than 6 h of driving.
   A fresh 16-week follow-up validated 7 h of slack for future launches, with a 92.62% worst week.
4. **A desk that can't lose its week**: every call journaled and replayed exactly after a crash
   (`desk/journal.py`, `desk/worldio.py`); a client that never sends a POST twice (`desk/client.py`);
   a live desk with a supervised stream and its own quote thread (`desk/live.py`).

Test final 3 (Sunday 01:00) ran with the same policy as the current launch script (8 h slack). Its score
is recorded above; the real final is Sunday 09:00. In test final 3 the desk attached at world minute 1205: it saw and quoted 824
of 1,036 requests, while 212 had already closed. Every request it saw was quoted, with 0.096 s p99 quote
latency. See [the runbook](docs/RUNBOOK.md) for the startup lesson and
[the sweep evidence](evidence/sweeps/) for policy validation. Practice results are not a final score.

## Run it

```sh
python3 -m venv .venv && .venv/bin/pip install https://spread.bahnexpress.com/kit/spread-0.1.0-py3-none-any.whl pytest jsonschema
printf 'SPREAD_URL=https://spread.bahnexpress.com\nSPREAD_KEY=<team key>\n' > .env   # never committed
.venv/bin/python -m pytest -q tests
.venv/bin/python -m desk.runner --level 8 --seed dev-1 --policy priced --param price_mult=1.5   # a practice week
sh tools/final_mac.sh                                                        # the final (see docs/RUNBOOK.md)
```

## Results dashboard

To browse saved ranking weeks and compare practice sweep settings locally:

```sh
.venv/bin/pip install -r requirements-dashboard.txt
.venv/bin/python -m streamlit run dashboard.py
```

The dashboard reads JSON evidence from `evidence/ranking_current/` and `evidence/sweeps/`. It does not contact
the game server or change results; use **Refresh evidence** after running more weeks.

## Evidence

- `proof/*.html`: one page per step (G0 reproduction, core, policy, live desk, adaptive price, margin pushes).
- `evidence/`: the sweeps, restart tests and rehearsals each page is built from (`tools/proof_*.py`).
- [`docs/PITCH.md`](docs/PITCH.md): seven-slide jury pitch, with the test final 3 score and operational finding.
- `docs/spread_spec.md`: the plan and the decision log (every decision with its seeds and run ids);
  `docs/spec_delta.md`: the plan checked line by line against the challenge's rules.
