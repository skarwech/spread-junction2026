#!/bin/sh
# Step 8 margin push, round 4: overnight fee hold and bulk-batch cap on the round 1-3 candidate.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8"
exec .venv/bin/python -m tools.sweep --name push6 --level 8 \
  --seeds dev-1 dev-3 hold-2 hold-5 v4-1 v4-3 v4-5 v4-8 \
  --setting "$BASE" \
  --setting "$BASE night_hold=1" \
  --setting "$BASE batch_cap=6" \
  --setting "$BASE batch_cap=10" \
  --setting "$BASE night_hold=1 batch_cap=6" \
  --setting "$BASE night_hold=1 fee_open=0.8" \
  --setting "$BASE night_hold=1 intake_cap=100" \
  --setting "$BASE night_hold=1 batch_cap=6 max_drive_h=7"
