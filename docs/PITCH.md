# Junction 2026 jury pitch — draft

Seven slides, ready to transfer into the submission deck. All money values are game euros.

## Slide 1 — The result

**Spread: a dispatch desk built to earn margin and stay above the 90% on-time gate.**

- Test final 3 (Sun 01:00) margin: **€5,912.57**; the real final is Sun 09:00, add its result here
- Won orders on time: **94.42%** · ranked: **yes** · 251 won orders, 0 undelivered
- Test final 3 leaderboard position: **36th**
- Test final 3 started at 01:00 Helsinki time; the desk attached at world minute 1205. It quoted 824/824 requests it saw (p99 0.096 s); 212/1,036 had already closed.
- Before the final: the 1.85× fee-cap policy ranked all 16 fresh L8 holdout weeks; its worst week was 92.41% on time.

*Speaker note:* The 1.85× cap is practice evidence; the headline above is the test final 3 result; replace it with the real final's.

## Slide 2 — One desk, three linked decisions

**Each quote commits us to a delivery problem.**

1. Quote the dealer's options at a price that can win and cover costs.
2. Set a gig fee that attracts a driver before the pickup deadline.
3. Post work the driver can complete on time; every won order counts against the 90% gate.

On the reference L8 week, the kit starter finished **unranked at −€72,612.51**. The desk's work is to protect the ranking threshold while changing the margin from negative to positive.

*Evidence:* [`evidence/g0/result.json`](../evidence/g0/result.json), [`proof/g0.html`](../proof/g0.html).

## Slide 3 — Price against the week, not one request

**Adapt the quote multiplier from observed wins and losses.**

- Start at 1.5× list; steer toward a 40% win rate.
- Update every 30 world minutes after at least five new outcomes, at most ±4% per update.
- Keep real quotes above 1.15× the typical fee; raise price when the last 24 hours' intake reaches 80 wins.

Across the same eight L8 weeks, the adaptive policy earned **€68,183** and its worst week was **94.8%** on time. Fixed 1.5× pricing earned **€66,209**, with a **93.3%** worst week. Both ranked 8/8.

*Evidence:* [`proof/adapt.html`](../proof/adapt.html), [`evidence/sweeps/adapt1.json`](../evidence/sweeps/adapt1.json).

## Slide 4 — Raise fees while drivers can see them

**A fee increase at night does not help a driver who will not read it until morning.**

- Open at 0.9× the typical fee.
- Increase in steps to 1.85× by two hours before the last pickup time.
- Hold the fee from 22:00 to 07:00, then resume increases during driver-active hours.

On 16 fresh paired L8 weeks, the 1.85× cap earned **€148,177** versus **€140,585** for the 2× cap, a gain of **€475/week**. It earned more on **14/16** paired weeks; both policies ranked 16/16, and worst on-time share was 92.41% versus 93.01%. The lower 1.75× cap made more money in some sweeps but missed the 92% buffer, so it was rejected.

*Evidence:* [`evidence/sweeps/feecap_hold3.json`](../evidence/sweeps/feecap_hold3.json), [`evidence/sweeps/feeprice_hold1.json`](../evidence/sweeps/feeprice_hold1.json), [`evidence/sweeps/feeprice_hold2.json`](../evidence/sweeps/feeprice_hold2.json).

## Slide 5 — Keep safe slower options in play

**If the fastest option is too tight, a slower option can still be a safe order.**

- Quote every offered option with at least 8 hours of slack and no more than 6 hours of driving.
- Decline only when no option passes that risk test.
- Test final 2 exposed the opportunity: 337 of 1,030 requests were declined; 166 had a slower option that the earlier policy did not quote.

On 16 fresh weeks, the step 8 policy earned **€143,934** versus **€123,805** for the previous policy (**+16.3%**). Both ranked 16/16; the worst on-time week improved from **90.6% to 93.2%**. This compares the whole policy change, including option coverage, risk limits, and overnight fee holds.

*Evidence:* [`proof/push8.html`](../proof/push8.html), [`evidence/sweeps/holdout9.json`](../evidence/sweeps/holdout9.json), [`evidence/rehearsal/tf2_leaderboard.json`](../evidence/rehearsal/tf2_leaderboard.json).

*Follow-up validation:* After test final 3, 16 fresh paired weeks supported lowering the slack threshold to 7 hours for future runs: 16/16 ranked, worst 92.62% on time, and +€231/week over the 8-hour setting. Test final 3 used 8 hours, and a later 8-seed sweep (next1) favoured 8 h again, so the launch script uses 8.

## Slide 6 — Recover without repeating actions

**The world continues when the process or connection fails.**

- Journal decisions and events so a restart rebuilds the same desk state.
- Do not resend a POST when its result is unknown; reconcile from the snapshot and event log.
- Supervise the event stream and reopen it from the last event sequence after a disconnect.

In the rehearsal of the previous launch config (fee cap 2×), the desk quoted **1,015/1,015** live requests in time across two SIGKILL runs; the rehearsal finished **96.9%** on time with **€16,428** margin. The fee-cap adjustment was validated in practice worlds, not another live rehearsal.

*Evidence:* [`proof/core.html`](../proof/core.html), [`proof/live.html`](../proof/live.html), [`evidence/rehearsal/wfe15af4fc63548624f3e.json`](../evidence/rehearsal/wfe15af4fc63548624f3e.json).

## Slide 7 — What we rejected and what remains unknown

- Raising the drive limit to 7+ hours reduced the worst-week safety margin to about 90.5–90.7%; the final cap stays at 6 hours.
- Earlier, higher fees for long drives, a per-batch quote cap, and lower opening fees lost margin in the sweeps.
- Changes to the adaptive controller did not repeat their tuning gains on fresh seeds; its 40% target and 30-minute, ±4% updates stayed unchanged.
- The final is one secret week. In test final 3 the 16 holdouts and live rehearsal did not predict its margin: ranked at 94.42%, €5,912.57.

*Evidence:* [`proof/push8.html`](../proof/push8.html), [`docs/spread_spec.md`](spread_spec.md#10-changelog-and-decision-log).

## Finalization checklist

- [ ] Confirm the final leaderboard position from the official leaderboard.
- [ ] Include the repository link and submission hash.
- [ ] Check every figure against its linked evidence and keep the final deck to 5–10 slides.
