# Final runbook and postmortem (Sunday 15 November, Helsinki time)

The runbook was written for a planned **08:00** start. The public final feed instead recorded
`startsAt=2026-11-14T23:00:00Z`, which is **01:00 Helsinki time** on 15 Nov; the final ended around 01:34.
The desk attached at world minute 1205, after 212 of 1,036 requests had already closed. Submissions closed
at **10:00**. For any rerun, trust `/v1/final` and `/v1/leaderboard` over the planned clock time, and start
the supervisor before the world begins.

## The night before

- Freeze the code after the final green test run. Do not run sweeps or change the launch policy once the live final window begins.
- Check the policy in `tools/start_final.sh`: `fee_open=0.9`, `fee_cap=1.85`, `target_win=0.4`, `intake_cap=80`, `trust_markup=0.01`, `options=safe`, `max_drive_h=6`, `min_slack_h=7`, `night_hold=1`. The fee cap and slack limit were each checked on 16 fresh paired L8 weeks; see the decision log. The completed 15 Nov final used `min_slack_h=8`. Once the desk has joined, `runs/<world>/live_meta.json` shows the params it actually loaded.
- Fallback (only if the step 8 desk misbehaves): the step 7 policy is `options=first min_slack_h=6 max_drive_h=5` without `night_hold` (git history of `tools/start_final.sh`, commit 104ef90).
- Plug the Mac into power. Note the Wi-Fi or use a wired connection.

## Pre-flight, before the final window

1. Mac on power, lid open, no other heavy programs, a stable network.
2. In the project folder:
   ```sh
   .venv/bin/python -m pytest -q tests        # all green
   ```
3. The key is in `.env` (never shown). The server answers:
   ```sh
   curl -s -o /dev/null -w "%{http_code}\n" https://spread.bahnexpress.com/v1/map   # 200
   ```
4. No sweeps or practice runs from now on: the practice limit drops to 20 requests a second while a final runs, and the desk needs the network.

## Start the desk before the world starts

```sh
sh tools/final_mac.sh
```

- It keeps the Mac awake (`caffeinate`) and restarts the desk if its process ever dies.
- It waits for a live final and ignores an ended final. Starting it after the world begins still joins that week, but it cannot quote requests that have already closed.
- Confirm that it prints the final world ID and begins receiving requests before assuming the desk is attached.

## During the final

- Watch the terminal: one score line per world day. Live ranking (no key, free): <https://spread.bahnexpress.com/leaderboard>.
- The desk's log: `runs/<final world id>/live.jsonl` (quotes, refusals, rejoins, stream errors).
- A line `spread: … Rejoining in 3 s` is normal: the desk lost a connection and rebuilt itself from the world.
- **If the terminal shows the shell prompt again before `End`:** run `sh tools/final_mac.sh` at once. Every second down loses requests to the competitor; the desk rebuilds from the world.
- Do not stop it by hand unless it is clearly broken. Ctrl-C stops it; the world goes on without it.

## After the end

- The terminal prints `End  margin €…`. Copy that line.
- `runs/<final world id>/live_summary.json` holds the score.
- The reveal opens after the end: `.venv/bin/python -m tools.rehearse --analyse <final world id> 0 > evidence/final.json` (unquoted requests, quote latency, rejoins).
- Put the result on the deck's first slide.

## By 10:00 submit on the Junction platform

- The submission hash (team page, <https://spread.bahnexpress.com/team>).
- The link to the code repository.
- The presentation (5–10 slides).

## Post-run finding

The final world `f88a11d932a63ddb3f413` placed **36th** and ended ranked at **€5,912.57**, 94.42% on time, with 251 won orders
and no undelivered orders. The reveal recorded 1,036 requests total: the desk saw and quoted 824, while 212
had already passed before it attached. At attachment, the world was at minute 1205 with no open requests.
Quote handling itself was fast (p99 0.096 s), with no stream errors, sequence gaps, or dropped events.

For a future run, launch as soon as the final world becomes available and confirm the live desk is attached
while requests are still arriving. The desk behaved correctly after attachment, but reconnection cannot
quote requests that have already closed. See [`evidence/final.json`](../evidence/final.json), the official
[`final_leaderboard.json`](../evidence/final_leaderboard.json), and the final's
[`live_summary.json`](../runs/f88a11d932a63ddb3f413/live_summary.json).
