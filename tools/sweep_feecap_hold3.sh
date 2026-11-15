#!/bin/sh
# Independent 16-week validation of the intermediate fee-cap candidates.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name feecap_hold3 --level 8 \
  --seeds fch3-1 fch3-2 fch3-3 fch3-4 fch3-5 fch3-6 fch3-7 fch3-8 \
          fch3-9 fch3-10 fch3-11 fch3-12 fch3-13 fch3-14 fch3-15 fch3-16 \
  --setting "$BASE fee_cap=2.0" \
  --setting "$BASE fee_cap=1.8" \
  --setting "$BASE fee_cap=1.85"
