#!/bin/sh
# Adaptive-price response sweep on six paired L8 seeds. The control is the frozen step 8 policy.
cd "$(dirname "$0")/.." || exit 1
BASE="priced price_mult=1.5 fee_mode=deadline fee_open=0.9 fee_cap=2.0 fee_lead_h=2 trust_markup=0.01 target_win=0.4 cost_floor=1.15 intake_cap=80 m_min=1.0 options=safe max_drive_h=6 min_slack_h=8 night_hold=1"
exec .venv/bin/python -m tools.sweep --name response1 --level 8 \
  --seeds resp-1 resp-2 resp-3 resp-4 resp-5 resp-6 \
  --setting "$BASE" \
  --setting "$BASE adapt_k=0.3" \
  --setting "$BASE adapt_k=0.9" \
  --setting "$BASE adapt_alpha=0.05" \
  --setting "$BASE adapt_alpha=0.2" \
  --setting "$BASE adapt_max_step=0.02" \
  --setting "$BASE adapt_max_step=0.06" \
  --setting "$BASE adapt_every=15" \
  --setting "$BASE adapt_every=60"
