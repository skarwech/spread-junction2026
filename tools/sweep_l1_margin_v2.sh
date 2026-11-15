#!/bin/sh
# Tune L1's one-step driver fee and quote risk filters against the uncapped, baseline-fee control.
cd "$(dirname "$0")/.." || exit 1
BASE="priced fee_mode=deadline fee_cap=1.0 fee_steps=1 options=safe min_slack_h=7"
exec .venv/bin/python -m tools.sweep --name l1_margin_v2 --level 1 \
  --seeds l1cap-a l1cap-b l1cap-c \
  --setting "$BASE fee_open=1.0 max_drive_h=6 open_order_cap=0" \
  --setting "$BASE fee_open=0.9 max_drive_h=6 open_order_cap=0" \
  --setting "$BASE fee_open=0.8 max_drive_h=6 open_order_cap=0" \
  --setting "$BASE fee_open=0.7 max_drive_h=6 open_order_cap=0" \
  --setting "$BASE fee_open=0.9 max_drive_h=5 open_order_cap=0" \
  --setting "$BASE fee_open=0.9 max_drive_h=4 open_order_cap=0" \
  --setting "$BASE fee_open=0.9 max_drive_h=6 open_order_cap=40"
