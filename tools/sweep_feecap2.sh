#!/bin/sh
# Fine sweep around the 1.75× candidate, looking for a better margin/safety trade-off.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name feecap2 --level 8 \
  --seeds fc-1 fc-2 fc-3 fc-4 fc-5 fc-6 \
  --setting "$BASE fee_cap=2.0" \
  --setting "$BASE fee_cap=1.75" \
  --setting "$BASE fee_cap=1.8" \
  --setting "$BASE fee_cap=1.85" \
  --setting "$BASE fee_cap=1.9"
