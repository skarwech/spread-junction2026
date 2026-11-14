#!/bin/sh
# Step 6, round 2: keep the cheaper opening fee but win back on-time buffer. Same 8 L8 seeds as push1.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_cap=2.0 min_slack_h=6 max_drive_h=5 trust_markup=0.01 cost_floor=1.15 m_min=1.0 target_win=0.4"
exec .venv/bin/python -m tools.sweep --name push2 --level 8 \
  --seeds dev-1 dev-3 hold-2 hold-5 v4-1 v4-3 v4-5 v4-8 \
  --setting "$BASE fee_open=0.9 fee_lead_h=3 intake_cap=80" \
  --setting "$BASE fee_open=0.9 fee_lead_h=2 intake_cap=70" \
  --setting "$BASE fee_open=0.85 fee_lead_h=3 intake_cap=80"
