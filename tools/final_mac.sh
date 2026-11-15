#!/bin/sh
# Final supervisor on this Mac: keeps it awake (caffeinate) and restarts the desk if its process dies.
# Start before the live final window; consult the server's current /v1/final status instead of a stale clock estimate.
# Stop with Ctrl-C after the final ends.
cd "$(dirname "$0")/.." || exit 1
while true; do
  caffeinate -dimsu sh tools/start_final.sh
  code=$?
  [ "$code" -eq 0 ] && break          # the week ended normally
  [ "$code" -eq 130 ] && break        # stopped by hand
  echo "desk exited with $code; restarting in 2 s (it rebuilds from the world)"; sleep 2
done
