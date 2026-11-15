#!/bin/sh
# Fresh-seed validation of the three leading response settings from response1.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name response_hold1 --level 8 \
  --seeds resp-h1 resp-h2 resp-h3 resp-h4 resp-h5 resp-h6 resp-h7 resp-h8 \
  --setting "$BASE" \
  --setting "$BASE adapt_alpha=0.2" \
  --setting "$BASE adapt_max_step=0.06" \
  --setting "$BASE adapt_k=0.3"
