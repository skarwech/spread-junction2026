#!/bin/sh
# Step 8 hold-out: the current final policy against the round 1-3 candidates on 8 fresh L8 seeds never used to choose.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0"
exec .venv/bin/python -m tools.sweep --name holdout8 --level 8 \
  --seeds ho8-1 ho8-2 ho8-3 ho8-4 ho8-5 ho8-6 ho8-7 ho8-8 \
  --setting "$BASE min_slack_h=6 max_drive_h=5 options=first" \
  --setting "$BASE min_slack_h=8 max_drive_h=6 options=safe" \
  --setting "$BASE min_slack_h=6 max_drive_h=6 options=safe" \
  --setting "$BASE min_slack_h=8 max_drive_h=7 options=safe"
