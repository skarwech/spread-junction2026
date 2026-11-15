#!/bin/sh
# Larger independent paired holdout for the lower fee-cap candidate.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name feeprice_hold2 --level 8 \
  --seeds fph2-1 fph2-2 fph2-3 fph2-4 fph2-5 fph2-6 fph2-7 fph2-8 \
          fph2-9 fph2-10 fph2-11 fph2-12 fph2-13 fph2-14 fph2-15 fph2-16 \
  --setting "$BASE" \
  --setting "$BASE fee_cap=1.75"
