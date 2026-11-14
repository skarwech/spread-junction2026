#!/bin/sh
# Starts the live desk for the team's (test) final with the step 3 policy. Safe to start early: it waits until a
# final is set and never joins one that has ended. Safe to restart at any time: it rebuilds from the world.
# Keep this machine awake (lid open, no sleep) until the week ends; if it stops, run this again at once.
cd "$(dirname "$0")/.." || exit 1
exec .venv/bin/python -u -m desk.live --final --level 8 --policy priced \
  --param price_mult=1.5 --param fee_mode=deadline --param fee_open=0.9 --param fee_cap=2.0 --param fee_lead_h=2 \
  --param min_slack_h=6 --param max_drive_h=5 --param trust_markup=0.01 \
  --param target_win=0.4 --param cost_floor=1.15 --param intake_cap=80 --param m_min=1.0
