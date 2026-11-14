#!/bin/sh
# Step 8 margin push, round 3: options=safe with the drive limit (6-8 h) and slack minimum (8-12 h) combined.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe"
exec .venv/bin/python -m tools.sweep --name push5 --level 8 \
  --seeds dev-1 dev-3 hold-2 hold-5 v4-1 v4-3 v4-5 v4-8 \
  --setting "$BASE max_drive_h=6 min_slack_h=8" \
  --setting "$BASE max_drive_h=7 min_slack_h=8" \
  --setting "$BASE max_drive_h=6 min_slack_h=10" \
  --setting "$BASE max_drive_h=7 min_slack_h=10" \
  --setting "$BASE max_drive_h=6 min_slack_h=12" \
  --setting "$BASE max_drive_h=7 min_slack_h=12" \
  --setting "$BASE max_drive_h=8 min_slack_h=10" \
  --setting "$BASE max_drive_h=6 min_slack_h=8 fee_open=1.0"
