#!/bin/sh
# Compare a real outstanding-order cap on L1 after making its fee schedule valid.
cd "$(dirname "$0")/.." || exit 1
BASE="priced fee_mode=deadline fee_open=1.0 fee_cap=1.0 fee_steps=1 options=safe max_drive_h=6 min_slack_h=7"
exec .venv/bin/python -m tools.sweep --name l1_capacity_v1 --level 1 \
  --seeds l1cap-a l1cap-b l1cap-c \
  --setting "$BASE open_order_cap=0" \
  --setting "$BASE open_order_cap=5" \
  --setting "$BASE open_order_cap=10" \
  --setting "$BASE open_order_cap=20" \
  --setting "$BASE open_order_cap=40" \
  --setting "$BASE open_order_cap=10 fee_open=0.9" \
  --setting "$BASE open_order_cap=10 fee_open=1.2"
