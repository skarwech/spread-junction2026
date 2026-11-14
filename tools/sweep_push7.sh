#!/bin/sh
# Step 8 margin push, round 5: long drives with an earlier (and higher) fee cap, on the candidate + night hold.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name push7 --level 8 \
  --seeds dev-1 dev-3 hold-2 hold-5 v4-1 v4-3 v4-5 v4-8 \
  --setting "$BASE" \
  --setting "$BASE long_drive_h=4 long_lead_h=8" \
  --setting "$BASE max_drive_h=7 long_drive_h=4 long_lead_h=8" \
  --setting "$BASE max_drive_h=7 long_drive_h=4 long_lead_h=12" \
  --setting "$BASE max_drive_h=7 long_drive_h=4 long_lead_h=8 long_cap=2.5" \
  --setting "$BASE max_drive_h=7 long_drive_h=5 long_lead_h=10" \
  --setting "$BASE max_drive_h=8 long_drive_h=4 long_lead_h=12 long_cap=2.5" \
  --setting "$BASE max_drive_h=9 long_drive_h=4 long_lead_h=12 long_cap=3.0"
