# Final-day runbook (Sunday 15 November, Helsinki time)

The final is one level 8 week. The organisers set it at **07:30**; it starts at **08:00** and ends at about **08:35**.
The desk runs on this Mac (team decision, 14 Nov). Submissions close at **10:00**.

## The night before

- Freeze the code. No sweeps, no edits to `desk/` or `tools/start_final.sh` after the last green test run.
- Check the policy in `tools/start_final.sh`: C with opening fee 0.9× (decision log, 14 Nov). Expected: `fee_open=0.9`, `target_win=0.4`, `intake_cap=80`, `trust_markup=0.01`, `min_slack_h=6`, `max_drive_h=5`.
- Plug the Mac into power. Note the Wi-Fi or use a wired connection.

## 07:00 pre-flight

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

## 07:15 start the desk

```sh
sh tools/final_mac.sh
```

- It keeps the Mac awake (`caffeinate`) and restarts the desk if its process ever dies.
- Before 07:30 it prints `No final running. Waiting…` (it also ignores the ended test finals: `/v1/final` keeps returning the last one).
- At 07:30 it prints `Final world f….` and the desk rebuilds from the world (no orders yet).

## 08:00–08:35 during the final

- Watch the terminal: one score line per world day. Live ranking (no key, free): <https://spread.bahnexpress.com/leaderboard>.
- The desk's log: `runs/<final world id>/live.jsonl` (quotes, refusals, rejoins, stream errors).
- A line `spread: … Rejoining in 3 s` is normal: the desk lost a connection and rebuilt itself from the world.
- **If the terminal shows the shell prompt again before `End`:** run `sh tools/final_mac.sh` at once. Every second down loses requests to the competitor; the desk rebuilds from the world.
- Do not stop it by hand unless it is clearly broken. Ctrl-C stops it; the world goes on without it.

## After the end (about 08:35)

- The terminal prints `End  margin €…`. Copy that line.
- `runs/<final world id>/live_summary.json` holds the score.
- The reveal opens after the end: `.venv/bin/python -m tools.rehearse --analyse <final world id> 0 > evidence/final.json` (unquoted requests, quote latency, rejoins).
- Put the result on the deck's first slide.

## By 10:00 submit on the Junction platform

- The submission hash (team page, <https://spread.bahnexpress.com/team>).
- The link to the code repository.
- The presentation (5–10 slides).
