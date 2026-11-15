#!/bin/sh
# Fresh paired validation of the 6.5 h drive limit under the selected 1.85x fee cap.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=1.85 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name safety_hold1 --level 8 \
  --seeds sh-1 sh-2 sh-3 sh-4 sh-5 sh-6 sh-7 sh-8 sh-9 sh-10 sh-11 sh-12 sh-13 sh-14 sh-15 sh-16 \
  --setting "$BASE" \
  --setting "$BASE max_drive_h=6.5"
