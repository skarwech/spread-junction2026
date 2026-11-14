#!/bin/sh
# Step 8 hold-out 2: current final policy, candidate, candidate + night hold, on 16 fresh L8 seeds (ho8 reruns
# double as a reproducibility check).
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0"
exec .venv/bin/python -m tools.sweep --name holdout9 --level 8 \
  --seeds ho8-1 ho8-2 ho8-3 ho8-4 ho8-5 ho8-6 ho8-7 ho8-8 ho9-1 ho9-2 ho9-3 ho9-4 ho9-5 ho9-6 ho9-7 ho9-8 \
  --setting "$BASE min_slack_h=6 max_drive_h=5 options=first" \
  --setting "$BASE min_slack_h=8 max_drive_h=6 options=safe" \
  --setting "$BASE min_slack_h=8 max_drive_h=6 options=safe night_hold=1"
