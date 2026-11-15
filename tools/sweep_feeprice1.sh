#!/bin/sh
# Fee schedule and adaptive-price floor sweep on six paired L8 seeds.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name feeprice1 --level 8 \
  --seeds fp-1 fp-2 fp-3 fp-4 fp-5 fp-6 \
  --setting "$BASE" \
  --setting "$BASE fee_cap=1.75" \
  --setting "$BASE fee_cap=2.25" \
  --setting "$BASE fee_steps=4" \
  --setting "$BASE fee_steps=8" \
  --setting "$BASE target_win=0.35" \
  --setting "$BASE m_min=1.1" \
  --setting "$BASE cost_floor=1.1" \
  --setting "$BASE cost_floor=1.2"
