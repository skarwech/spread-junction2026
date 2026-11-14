#!/bin/sh
# Step 6 margin push: policy C against a lower opening fee and a higher win target, same 8 L8 seeds.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_cap=2.0 fee_lead_h=2 min_slack_h=6 max_drive_h=5 trust_markup=0.01 cost_floor=1.15 intake_cap=80 m_min=1.0"
exec .venv/bin/python -m tools.sweep --name push1 --level 8 \
  --seeds dev-1 dev-3 hold-2 hold-5 v4-1 v4-3 v4-5 v4-8 \
  --setting "$BASE fee_open=1.0 target_win=0.4" \
  --setting "$BASE fee_open=0.9 target_win=0.4" \
  --setting "$BASE fee_open=0.8 target_win=0.4" \
  --setting "$BASE fee_open=1.0 target_win=0.5" \
  --setting "$BASE fee_open=0.9 target_win=0.5"
