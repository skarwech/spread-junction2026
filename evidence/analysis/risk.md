# Lateness risk at quote time

14 Nov 2026. Every number below is printed by `evidence/analysis/risk.py`, and the full printout is saved as `evidence/analysis/risk_out.txt`. "Sx" refers to a section of that printout. To reproduce:

    .venv/bin/python -m evidence.analysis.risk > evidence/analysis/risk_out.txt     # a few minutes, no network, no worlds created

## Bottom line

1. **The model ranks orders well, from what the desk knows at quote time.**
   - On six hold-out seeds it was never fitted on: AUC 0.835, AUC within a run 0.755, calibration intercept +0.12 and slope 0.96 (S11).
   - Leave-one-seed-out on the dev seeds: pooled AUC 0.848, mean AUC within a run 0.783 (S4). This figure is slightly optimistic, because the compact model F was picked on it.
2. **The level of risk is set by the world, not by the request.** The model cannot see how short of drivers a world is. On the regime-R weeks played without a filter, its error in the week's late share has a standard deviation of 4.5 points, and in the worst week it under-predicts by 6.4 points (S12).
3. **What matters:** slack, measured as the room left in the best single working day; how many open orders we hold; trade-ins; premium cars; private pickups; and our own late share so far this week.
   - **What does not matter:** weekday, arrival hour, the option kind once slack is in, EVs under 30%, the dealer's note (little), fixed pickup or delivery towns, and our policy parameters.
4. **Price of lateness.**
   - The expected lateness cost of an order is **p × 0.37 × price + €175 × (p − 0.10)**. The second term is the cost of breaching the 90% gate.
   - Net of this cost, realized margin turns negative above p ≈ 0.15–0.20 (S15).
5. **Rule: decline when P(late) > 0.10.**
   - Not 0.15. Declining keeps our open orders low, which lowers the model's P(late) and lets it accept more. Replayed with that feedback, 0.15 accepts too much (S10d).
   - The rule beats the slack/drive filter replayed the same way. It does not guarantee the gate: no rule replayed here keeps the worst weeks at 90% (S10d).

   | Rule | Replay with state (S10d) | As actually played (S10c-real) |
   |---|---|---|
   | P(late) > 0.10 | €45,750 · 7 of 10 weeks ≥ 0.90 · worst 0.837 | not played yet |
   | P(late) > 0.15 | €49,201 · 6 of 10 · worst 0.822 | not played yet |
   | slack < 6 h or drive > 5 h | €40,484 · 6 of 10 · worst 0.767 | **€60,490 · 8 of 10 · worst 0.867** |

   - **The replay is pessimistic.** It keeps the outcomes of the week that accepted everything. When the filter was actually played, it made €20k more and passed in 2 more weeks than its replay. That gap is the drivers freed by declining.
   - **Next step:** play `max_p_late` = 0.10 against the slack/drive filter before adopting it.

## 1. Data

- **Runs.** All won orders of the L8 `priced` runs with a `summary.json`, minus `wc721c95a136b417e5d7c`.
  - **Dev:** seeds dev-1 to dev-4 (`risk_data.PINNED`). Five runs that repeat the same seed and params were dropped, because a world replays exactly, which leaves 46 runs.
  - **Hold:** seeds hold-1 to hold-6, the 18 runs of sweep holdout1. No model was fitted on them. The decline threshold, however, was chosen with their replay tables in view, so for the threshold they are no longer a clean test.
- **Late** means the order has a `late_refund` or `undelivered_penalty` line. These labels give the server's final `onTimeShare` exactly in 53 of 64 runs, and to within 0.004 in the rest (S1c). The gap is the 13 orders dropped below.
- **Margins** are sums over orders. They run above the server's margin by €87 per run (median), with a mean of €151 and a maximum of €778 (S1c). The difference is ledger lines that cannot be tied to a kept order.
- **Dropped orders.** 13 orders without revenue, penalty or cancellation (9 of them in `w4d8473c66bf47b0aa6e9`), and 2 `within_3_days` orders.
- **Regime R** is price ×1.5 with `fee_mode=deadline`, the regime we would play.

| | Runs | Won orders | Late | Undelivered |
|---|---|---|---|---|
| Dev, all policies | 46 | 15,325 | 21.1% | 141 |
| Dev, regime R | 20 | 5,551 | 2.4% to 15.1% by seed | |
| Hold, all regime R | 18 | 5,951 | 16.8% | 4 |

Regime R played without a filter (the fees1 and holdout1 runs) is late 3.4% to 37.6% of the time, depending on the seed (S1). The world matters more than anything about the request.

## 2. Which features matter, one at a time (S2, dev)

Late share by level, over all dev orders. "R" is regime R only.

| Feature | Levels: late share all dev (R) |
|---|---|
| **Slack, task definition** (deadline − max(ready, respondBy) − road minutes) | <2 h 0.85 (0.93) · 2–4 h 0.57 (0.46) · 4–6 h 0.39 (0.29) · 6–8 h 0.24 (0.15) · 8–12 h 0.10 (0.04) · **12–24 h 0.30 (0.21)** · 24–36 h 0.15 (0.05) · ≥36 h 0.16 (0.10) |
| **Best-day slack** (the most spare time in one working day, 07:00–20:00 Mon–Fri, between start and deadline) | <2 h 0.94 · 2–4 h 0.58 (0.46) · 4–6 h 0.42 (0.34) · 6–8 h 0.28 (0.18) · 8–10 h 0.15 (0.06) · ≥10 h 0.10 (0.05) |
| Drive hours | <1 h 0.17 · 1–2 h 0.12 · 2–3 h 0.15 · 3–4 h 0.21 · 4–5 h 0.30 · 5–6 h 0.40 · 6–8 h 0.52 · ≥8 h 0.61 |
| Two legs (trade-in) | 0.65 vs 0.20 (R: 0.54 vs 0.11). 249 orders |
| Premium | 0.43 vs 0.20 (R: 0.27 vs 0.11) |
| Private pickup / private delivery | 0.34 vs 0.20 / 0.37 vs 0.20 |
| EV under 30% | 0.31 vs 0.21 (R: 0.16 vs 0.11) |
| Note present | 0.23 vs 0.20 (R: 0.14 vs 0.09) |
| Kind | same_day 0.26, next_day 0.18 |
| Weekday of arrival | Mon 0.12 · Tue 0.21 · Wed 0.21 · Thu 0.29 · Fri 0.23 |
| Arrival hour | <10 0.24 · 10–12 0.22 · 12–14 0.26 · 14–16 0.20 · ≥16 0.18 |
| Our open orders at arrival | <20 0.05 · 20–40 0.07 · 40–80 0.13 · 80–160 0.21 · ≥160 0.46 |
| Our late share so far (matured orders) | <0.1 0.11 · 0.1–0.2 0.18 · 0.2–0.3 0.40 · ≥0.3 0.54 |

**Why the task's slack is not monotone.** In the 12–24 h band, 911 of 1,099 orders are `next_day`, and they are late 33% of the time. A `next_day` slack of 12–24 h means a car that is ready late, or a long drive: the whole job must fit into the next working day, while the 11 night hours count as slack.

Best-day slack counts only time a car can move, and it is monotone. It needs a new parameter, because `min_slack_h` cannot express it.

Both slack measures use the units of `desk.policy.risk()`: a same-place leg counts 0 road minutes, where `map.json` says 25.

**Places do not carry over between worlds.** We compared each town's late share across seed pairs, using towns with at least 40 orders in both seeds (S3).

| Side | Mean Spearman | Range |
|---|---|---|
| Pickup town | +0.22 | 0.00 to +0.73 |
| Delivery town | +0.36 | +0.18 to +0.52 |

This matches RULES.md: the shortage of each town is drawn new in every world. Only a structural part, delivery towns where few drivers live, repeats.

## 3. Models and leave-one-seed-out validation (S4)

**Models.** All are ridge logistic regressions, each fitted on 3 dev seeds and tested on the 4th.
- A, B, B′, C, D and E were fixed before any results were seen.
- F was picked afterwards, from the drop-one results (S7) and the LOSO comparison of compact variants (S7b), so its LOSO numbers are slightly optimistic. Its hold-out numbers are not.
- The context terms are our open orders, `price_mult` and `fee_mode`. All are known to the desk.

| Model | Features | LOSO pooled AUC | LOSO mean AUC within run (min seed) | LOSO log-loss | Hold pooled AUC / AUC within run / log-loss |
|---|---|---|---|---|---|
| M0 | Base rate of the training seeds | – | – | 0.532 | – |
| A | Slack bands (task definition) + context | 0.792 | 0.714 (0.645) | 0.419 | 0.815 / 0.717 / 0.353 |
| B | All task features (slack bands, drive, kind, legs, private, premium, EV, note, weekday, hour) + context | 0.834 | 0.766 (0.667) | 0.387 | 0.840 / 0.764 / 0.337 |
| B′ | B with best-day slack hinges in place of slack bands | 0.834 | 0.766 (0.666) | 0.386 | 0.844 / 0.766 / 0.334 |
| C | B + town codes (target-encoded on the training seeds) | 0.837 | 0.768 (0.676) | 0.384 | 0.845 / 0.775 / 0.333 |
| D | B + our late share so far (week, and pickup town) | 0.839 | 0.766 (0.647) | 0.380 | 0.838 / 0.765 / 0.337 |
| E | B′ + online | 0.839 | 0.769 (0.653) | 0.379 | 0.842 / 0.763 / 0.334 |
| **F** | **Compact (below)** | **0.848** | **0.783 (0.681)** | **0.372** | **0.835 / 0.755 / 0.340** |

**F has the lowest scores of B to F on the hold seeds**, both for AUC within a run (0.755 against 0.763–0.775) and for log-loss (0.340 against 0.333–0.337). Picking it on LOSO (S7b) overfit a little. The models differ by at most 0.02 in AUC, so F stays for its simplicity. If the extra features cost nothing to compute, E is an equal or slightly better alternative under the same rule.

### Per held-out seed, model F (AUC and calibration)

LOSO, dev seeds, all runs of the seed. The "R" columns are regime-R orders only.

| Held-out seed | n | Observed | Predicted | AUC | AUC within run | Calibration intercept | Calibration slope | R observed | R predicted | R AUC |
|---|---|---|---|---|---|---|---|---|---|---|
| dev-1 | 6,182 | 0.281 | 0.214 | 0.868 | 0.839 | +0.80 | 1.22 | 0.130 | 0.100 | 0.858 |
| dev-2 | 2,942 | 0.125 | 0.200 | 0.852 | 0.797 | −0.96 | 0.80 | 0.024 | 0.030 | 0.833 |
| dev-3 | 4,255 | 0.224 | 0.215 | 0.836 | 0.815 | +0.10 | 1.03 | 0.151 | 0.148 | 0.822 |
| dev-4 | 1,946 | 0.092 | 0.118 | 0.757 | 0.681 | −0.92 | 0.62 | 0.055 | 0.058 | 0.726 |

External test: fitted on all four dev seeds, tested on the hold seeds (S11).

| Hold seed | n | Observed | Predicted | AUC | AUC within run | Calibration intercept | Calibration slope |
|---|---|---|---|---|---|---|---|
| hold-1 | 1,280 | 0.210 | 0.166 | 0.848 | 0.800 | +0.51 | 1.07 |
| hold-2 | 1,501 | 0.253 | 0.221 | 0.830 | 0.799 | +0.22 | 0.97 |
| hold-3 | 856 | 0.069 | 0.112 | 0.824 | 0.760 | −0.77 | 0.94 |
| hold-4 | 733 | 0.067 | 0.081 | 0.829 | 0.749 | −0.50 | 0.87 |
| hold-5 | 957 | 0.215 | 0.145 | 0.753 | 0.737 | +0.24 | 0.78 |
| hold-6 | 624 | 0.058 | 0.097 | 0.763 | 0.683 | −1.10 | 0.74 |

**Calibration bins** (S5: regime R, dev, out-of-fold). The model is right on average up to p = 0.2, and under-predicts above it.

| Predicted band | Predicted | Observed | n |
|---|---|---|---|
| 0–0.05 | 0.024 | 0.027 | 2,694 |
| 0.05–0.10 | 0.071 | 0.063 | 1,253 |
| 0.10–0.20 | 0.140 | 0.155 | 851 |
| 0.20–0.30 | 0.243 | 0.321 | 305 |
| 0.30–0.50 | 0.382 | 0.467 | 274 |
| 0.50–1 | 0.659 | 0.672 | 174 |

**What the per-seed table says.**
- The ranking holds in every seed: AUC within a run is 0.68 to 0.84.
- The level shifts with the world: calibration intercepts run from −1.10 to +1.20.
- In bad worlds the model is too low (dev-1, hold-1, hold-5), and in good worlds too high (dev-2, hold-3, hold-6).

On the 10 regime-R weeks played without a filter, the error of the week's late share (observed − predicted) is (S12):

| Measure | Value |
|---|---|
| Mean | −0.008 |
| Standard deviation | 0.045 |
| Worst under-prediction | +0.064 (hold-5) |

Our own late share so far is the only signal of the world's shortage. It helps calibration, at +0.007 log-loss when dropped, but it reacts late, because orders only mature after their deadline.

## 4. What each feature is worth

**Drop one group at a time** (S7). Each figure is the change in mean AUC within a run and in pooled log-loss when the group is removed. A negative ΔAUC or a positive Δlog-loss means the group helps.

| Group | From B (task features): ΔAUC / Δlog-loss | From E (best-day slack + online): ΔAUC / Δlog-loss | Verdict |
|---|---|---|---|
| Slack (bands / best-day hinges) | −0.032 / +0.020 | −0.044 / +0.021 | **Matters most** |
| Drive hours | −0.039 / +0.025 | +0.006 / +0.000 | Matters with the task slack; redundant once best-day slack is used |
| Open orders | +0.012 / **+0.053** | +0.003 / +0.019 | **Matters for calibration**: load sets the level |
| Private (pickup, delivery) | −0.014 / +0.002 | −0.015 / +0.003 | Matters (pickup OR 1.9) |
| Two legs | +0.001 / −0.000 | −0.010 / +0.002 | Large effect on few orders (OR 8.3) |
| Premium | −0.001 / +0.003 | −0.002 / +0.004 | Large effect on few orders (OR 3.9, same sign in all 4 folds) |
| Online late share | – | −0.003 / +0.007 | Helps calibration |
| Note | +0.000 / +0.001 | −0.002 / +0.001 | Small (OR 1.37) |
| Kind | −0.002 / +0.001 | +0.000 / −0.000 | No effect once slack is in (OR 0.98 in E, sign flips by fold) |
| EV under 30% | +0.001 / −0.000 | +0.002 / −0.000 | No |
| Weekday | +0.004 / −0.001 | +0.001 / −0.002 | No (only Thu is consistent; the rest is load) |
| Arrival hour | +0.006 / +0.004 | +0.006 / +0.001 | No |
| Policy (`price_mult`, `fee_mode`) | −0.003 / **−0.011** | +0.001 / −0.009 | Hurts out of seed: open orders already carries the load |
| Towns (C vs B) | +0.002 AUC LOSO, +0.011 hold | | Little; the shortage is redrawn per world |

**Scorecard, model F.** Fitted on all dev data (S6). Every coefficient has the same sign in all 4 LOSO fits.

```
logit P(late) = −7.210
  + 0.402 × max(0, 10 − best-day slack h)     (OR 1.50 per hour short of 10 h)
  + 0.138 × min(drive h, 10)                  (OR 1.15 per hour)
  + 2.118 × [two legs]                        (OR 8.3)
  + 0.639 × [private pickup]                  (OR 1.9)
  − 0.556 × [private delivery]                (OR 0.57: its booked-hour deadline is already in the slack)
  + 1.354 × [premium]                         (OR 3.9)
  + 0.314 × [note present]                    (OR 1.37)
  + 1.113 × ln(1 + open orders)               (OR 3.0 per e-fold of our book)
  + 0.476 × logit(s)                          s = (late + 1.5) / (matured + 10) over our orders whose deadline has passed
  + 0.127 × (logit(s_town) − logit(s))        s_town = (late_town + 5 s) / (matured_town + 5), same pickup town
```

**Inputs.**
- Best-day slack is `risk_data.best_day_slack(start, deadline, drive minutes)`, where start = max(first pickup window `from`, `respondBy`).
- Drive hours come from `policy.risk()`.
- Open orders are won orders without a revenue line yet.

## 5. From P(late) to a price

**Severity** (S8). Given that an order is late, the expected loss is a share of its price. Undelivered counts as 3: the price is lost and 2× is paid.

| Data | Expected share given late | 10% | 25% | 50% | 100% | Undelivered |
|---|---|---|---|---|---|---|
| Dev regime R | 0.366 | 6% | 61% | 30% | 1% | 1% |
| Hold | 0.366 | 6% | 55% | 36% | 3% | 0% |
| Dev, all runs | 0.497 | | | | | 4% |

Regime R is the case that applies to us: its tier mix is close in dev and hold. The all-dev figure is higher because it includes overloaded runs. By slack band the expected share is about 0.32–0.40, but 0.56 below 2 h of slack.

**The 90% gate as a price** (S14). Each order uses (p − 0.10) of the week's late budget. The shadow price is λ = V·φ(z)/(σ·N), with these inputs:

| Input | Value |
|---|---|
| V, median margin of the 19 ranked regime-R filtered runs | €5,343 (€3,531–9,388) |
| N, median won orders of those runs | 207 |
| σ, sd of the week's late share (model error 0.045 and binomial noise) | 0.049 |
| Target late share | 7% (z = 0.62) |

This gives **λ ≈ €175 per unit of P(late)**. The range of V gives €116–307, and a target of 6% or 8% gives €151 or €193.

The trust loss of level 8 (a late order halves that dealer's count) is not costed here. It argues for the lower end of the threshold.

**Expected lateness cost per order:**

> **C(p) = p × 0.37 × quote + €175 × (p − 0.10)**

| p | C(p) on a €120 quote | Note |
|---|---|---|
| 0.05 | −€6.5 | Safe orders buy gate room |
| 0.10 | +€4.4 | |
| 0.15 | +€15.4 | |
| 0.20 | +€26.4 | |
| 0.30 | +€48.3 | |

The refund part, p × 0.37 × price, matches the refunds actually paid in the middle bands (S9, dev and hold).

**Realized margin per order, net of the gate cost** (S15, regime R).

| P(late) band | Dev (LOSO) | Hold |
|---|---|---|
| 0–0.05 | +€37.8 | +€38.4 |
| 0.05–0.10 | +€23.7 | +€28.8 |
| 0.10–0.15 | +€7.7 | +€15.8 |
| 0.15–0.20 | **−€1.6** | **+€8.4** |
| 0.20–0.30 | −€32.1 | −€13.4 |
| 0.30–0.50 | −€109.2 | −€55.6 |
| 0.50–1 | −€221.0 | −€184.2 |

Before the gate cost, an order breaks even at about p = 0.2–0.3 in dev and 0.3–0.5 in hold (S9). With it, the break-even is p ≈ 0.15–0.20.

**Add to the quote, or decline?** Adding C(p) to the quote turns into a decline in practice. At p = 0.15, C(p) is about +13% of the quote. Without a filter, raising the price from ×1.5 to ×1.65 cut won orders by 30–66% (S1b: dev-1 439 → 300, dev-2 145 → 61, dev-3 444 → 311, dev-4 208 → 70). Markups were never tested.

## 6. Replays of decline rules (S10, S10b–d)

**What every replay keeps fixed.** Each one replays the 10 regime-R weeks that were played without a filter (4 dev, 6 hold). It keeps the outcomes of the orders that week won, and it cannot show the drivers that declining would free. All replays are therefore pessimistic.
- A real filtered run beat its own replay by 1.9 points of on-time share on average (median +1.5, range −4.5 to +12.3) and by €1,394 of margin, over 28 pairs (S10b).
- Over the 10 weeks, the filter as played made €60,490 and passed 8 times; its replay shows €40,484 and 6 passes (S10c-real).

**State-blind replay** (S10, S10c). Each order is scored with the open orders and late share of the week that accepted everything. At p* = 0.15 this shows 9 of 10 weeks at or above 0.90, worst 0.876, and €44,945. That overstates the rule: live, declining keeps the book small, so later requests score lower and are accepted.

**State-consistent replay** (S10d). In arrival order, open orders and the late shares so far are counted over accepted orders only, and each request is re-scored by its fold's model. Each cell is the on-time share, then the margin in euros.

| Week | P>0.05 | P>0.10 | P>0.15 | P>0.20 | P>0.10 or slack<6\|drive>5 | slack<6\|drive>5 only (replay) |
|---|---|---|---|---|---|---|
| dev-1 | 0.958 / 5,132 | 0.944 / 6,513 | 0.933 / 6,871 | 0.919 / 6,819 | 0.945 / 5,558 | 0.940 / 5,662 |
| dev-2 | 0.992 / 4,032 | 0.977 / 4,505 | 0.971 / 4,624 | 0.971 / 4,886 | 1.000 / 3,639 | 1.000 / 3,639 |
| dev-3 | 0.957 / 3,392 | 0.933 / 3,191 | 0.898 / 3,308 | 0.883 / 3,217 | 0.930 / 2,714 | 0.896 / 2,601 |
| dev-4 | 0.929 / 2,385 | 0.929 / 3,210 | 0.930 / 3,781 | 0.927 / 3,939 | 0.934 / 2,091 | 0.934 / 2,091 |
| hold-1 | 0.919 / 4,468 | 0.886 / 4,906 | 0.857 / 4,845 | 0.841 / 4,622 | 0.886 / 4,978 | 0.838 / 5,312 |
| hold-2 | 0.855 / 4,124 | 0.837 / 5,041 | 0.822 / 5,205 | 0.805 / 5,518 | 0.838 / 4,516 | 0.767 / 3,884 |
| hold-3 | 0.973 / 5,181 | 0.968 / 6,591 | 0.967 / 7,453 | 0.961 / 7,651 | 0.970 / 5,703 | 0.960 / 6,122 |
| hold-4 | 0.976 / 3,589 | 0.948 / 3,806 | 0.934 / 4,076 | 0.924 / 4,088 | 0.969 / 3,588 | 0.965 / 3,777 |
| hold-5 | 0.877 / 3,140 | 0.858 / 3,497 | 0.843 / 3,863 | 0.831 / 3,986 | 0.850 / 3,234 | 0.802 / 3,084 |
| hold-6 | 0.974 / 3,772 | 0.949 / 4,489 | 0.947 / 5,174 | 0.946 / 5,634 | 0.958 / 4,150 | 0.954 / 4,312 |
| **Total €** | 39,215 | **45,750** | 49,201 | 50,360 | 40,169 | 40,484 |
| **Weeks ≥ 0.90** | 8 | **7** | 6 | 6 | 7 | 6 |
| **Worst on-time** | 0.855 | **0.837** | 0.822 | 0.805 | 0.838 | 0.767 |

**Reading the replay.**
- On the same pessimistic basis, P > 0.10 beats the slack/drive filter: €5,266 more margin, one more week at 0.90, and a worst week 7 points better.
- Adding the filter on top of P > 0.10 costs margin and gains nothing.
- **Hold-1, hold-2 and hold-5 stay below 0.90 under every rule**, including P > 0.05. Only the real filtered runs show what freeing drivers is worth: 0.915, 0.890 and 0.867 for slack ≥ 6 h and drive ≤ 5 h (S10c-real).
- No request-level rule shown here guarantees the gate in the worst worlds.

**Adaptive variants did not beat a fixed threshold** in the state-blind replay (S13, S13b):
- An online late budget, accepting while the projected late share stays ≤ 6% or 8%, with or without re-scaling by realized lateness.
- A switch to 0.10 while our realized late share is above 7%.

## 7. Recommendation

- **Score each request with model F** at quote time. The inputs are best-day slack, drive, two legs, private pickup or delivery, premium, note, our open orders, and our late share so far (for the week and for the pickup town).
- **Decline when P(late) > 0.10**, by quoting `decline_mult` × list. Otherwise quote `price_mult` = 1.5 × list as now.
  - Add a parameter `max_p_late = 0.10`, in place of `min_slack_h` and `max_drive_h`.
  - The economics (S15) would allow 0.15. The state-consistent replay (S10d) shows the open-orders feedback, and the gate is hard, so the lower value is the default.
- **If the rule is costed rather than thresholded,** use C(p) = p × 0.37 × quote + €175 × (p − 0.10), and decline when the quote plus C(p) would exceed about 1.65 × list, where wins become rare (S1b).
- **Validate before adopting.** The only real evidence is for the slack/drive filter: 8 of 10 weeks, worst 0.867, €60,490. Play `max_p_late` = 0.10 and 0.15 against slack ≥ 6 h and drive ≤ 5 h on dev-1 to dev-4, and on fresh seeds, since the hold seeds have now informed the threshold. Adopt the model rule only if it matches the filter's pass count.

## Caveats

- **The model is trained on one desk's logistics** (the starter's posting, with starter or deadline fees). A desk that moves cars differently changes P(late), mostly through the intercept. The open-orders and online terms absorb part of that.
- **The online terms need our own matured orders.** On Monday they rest on the prior, 15% late, so early quotes rely on the request features and on open orders alone.
- **Note deadlines are not parsed here.** A note that tightens the deadline shows up only through "note present".
- **The trust cost of level 8 and the competitor's response to our declines are not modelled.**
