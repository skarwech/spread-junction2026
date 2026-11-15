#!/bin/sh
# Hold out four fresh L1 seeds while tuning the one-step fee and safe route limits.
cd "$(dirname "$0")/.." || exit 1
BASE="priced fee_mode=deadline fee_cap=1.0 fee_steps=1 options=safe"
exec .venv/bin/python -m tools.sweep --name l1_holdout_v3 --level 1 \
  --seeds l1ho-1 l1ho-2 l1ho-3 l1ho-4 \
  --setting "$BASE fee_open=0.9 max_drive_h=6 min_slack_h=7 open_order_cap=0" \
  --setting "$BASE fee_open=0.9 max_drive_h=4 min_slack_h=7 open_order_cap=0" \
  --setting "$BASE fee_open=0.85 max_drive_h=6 min_slack_h=7 open_order_cap=0" \
  --setting "$BASE fee_open=0.85 max_drive_h=4 min_slack_h=7 open_order_cap=0" \
  --setting "$BASE fee_open=0.8 max_drive_h=6 min_slack_h=7 open_order_cap=0" \
  --setting "$BASE fee_open=0.8 max_drive_h=4 min_slack_h=7 open_order_cap=0" \
  --setting "$BASE fee_open=0.8 max_drive_h=4 min_slack_h=8 open_order_cap=0"
