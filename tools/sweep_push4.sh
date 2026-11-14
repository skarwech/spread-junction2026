#!/bin/sh
# Step 8 margin push, round 2: on top of options=safe, volume (intake cap, win target), limits and opening fee.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe"
exec .venv/bin/python -m tools.sweep --name push4 --level 8 \
  --seeds dev-1 dev-3 hold-2 hold-5 v4-1 v4-3 v4-5 v4-8 \
  --setting "$BASE" \
  --setting "$BASE intake_cap=120" \
  --setting "$BASE target_win=0.5 intake_cap=120" \
  --setting "$BASE target_win=0.45" \
  --setting "$BASE max_drive_h=6" \
  --setting "$BASE min_slack_h=4" \
  --setting "$BASE min_slack_h=8" \
  --setting "$BASE fee_open=0.8"
