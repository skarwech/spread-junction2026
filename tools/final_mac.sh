#!/bin/sh
# Sunday final on this Mac: keeps the Mac awake (caffeinate) and restarts the desk if its process ever dies.
# Start before 07:30 (the final is set at 07:30, starts 08:00, ends ~08:35). Stop with Ctrl-C after the end.
cd "$(dirname "$0")/.." || exit 1
while true; do
  caffeinate -dimsu sh tools/start_final.sh
  code=$?
  [ "$code" -eq 0 ] && break          # the week ended normally
  [ "$code" -eq 130 ] && break        # stopped by hand
  echo "desk exited with $code; restarting in 2 s (it rebuilds from the world)"; sleep 2
done
