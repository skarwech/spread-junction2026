#!/bin/sh
# Test whether slightly wider risk limits improve margin without breaking the 92% on-time buffer.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=1.85 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name safety1 --level 8 \
  --seeds sr-1 sr-2 sr-3 sr-4 sr-5 sr-6 sr-7 sr-8 \
  --setting "$BASE" \
  --setting "$BASE min_slack_h=7" \
  --setting "$BASE max_drive_h=6.5" \
  --setting "$BASE min_slack_h=7 max_drive_h=6.5"
