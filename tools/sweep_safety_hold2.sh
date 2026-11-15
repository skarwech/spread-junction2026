#!/bin/sh
# Fresh paired validation of the 7 h slack limit under the selected 1.85x fee cap.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=1.85 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name safety_hold2 --level 8 \
  --seeds sv-1 sv-2 sv-3 sv-4 sv-5 sv-6 sv-7 sv-8 sv-9 sv-10 sv-11 sv-12 sv-13 sv-14 sv-15 sv-16 \
  --setting "$BASE" \
  --setting "$BASE min_slack_h=7"
