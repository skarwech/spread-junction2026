#!/bin/sh
# Fresh-seed validation of the leading fee cap and win-target settings from feeprice1.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name feeprice_hold1 --level 8 \
  --seeds fph-1 fph-2 fph-3 fph-4 fph-5 fph-6 fph-7 fph-8 \
  --setting "$BASE" \
  --setting "$BASE fee_cap=1.75" \
  --setting "$BASE target_win=0.35"
