#!/bin/sh
# Practice sweep after the final: the launch policy (slack 7 h) against the final's slack 8 h and a 1.8x fee cap, on 8 fresh L8 seeds.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 night_hold=1"
exec .venv/bin/python -m tools.sweep --name next1 --level 8 \
  --seeds nx-1 nx-2 nx-3 nx-4 nx-5 nx-6 nx-7 nx-8 \
  --setting "$BASE fee_cap=1.85 min_slack_h=7" \
  --setting "$BASE fee_cap=1.85 min_slack_h=8" \
  --setting "$BASE fee_cap=1.8 min_slack_h=7"
