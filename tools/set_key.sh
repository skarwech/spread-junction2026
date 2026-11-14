#!/bin/sh
# Stores the Spread team key in .env without echoing it, logging it or putting it in shell history,
# then checks it against the server (prints only the HTTP status). Keeps the other .env settings.
cd "$(dirname "$0")/.." || exit 1
umask 077
old_tty=$(stty -g 2>/dev/null)
tmp=
cleanup() {
  [ -n "$old_tty" ] && stty "$old_tty" 2>/dev/null
  [ -n "$tmp" ] && rm -f "$tmp"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

url=$(grep '^SPREAD_URL=' .env 2>/dev/null | head -n 1 | cut -d= -f2-)
[ -n "$url" ] || url=https://spread.bahnexpress.com
printf 'Paste your Spread team key (from %s/join), then press Enter: ' "$url"
stty -echo
IFS= read -r key
stty echo
printf '\n'
key=$(printf '%s' "$key" | tr -d '[:space:]')
if [ -z "$key" ]; then
  echo "No key entered; .env unchanged."
  exit 1
fi

tmp=$(mktemp .env.XXXXXX) || exit 1
if [ -f .env ]; then
  grep -v '^SPREAD_KEY=' .env > "$tmp"
  [ $? -le 1 ] || { echo ".env is unreadable; unchanged." >&2; exit 1; }
fi
printf 'SPREAD_KEY=%s\n' "$key" >> "$tmp" || exit 1
mv "$tmp" .env || { echo "Could not write .env; unchanged." >&2; exit 1; }
tmp=

code=$(printf 'Authorization: Bearer %s\n' "$key" | curl -s -o /dev/null -w '%{http_code}' -H @- "$url/v1/worlds")
case "$code" in
  200) echo "Saved to .env. The server accepts the key (HTTP 200). You can close this tab." ;;
  401) echo "Saved to .env, but the server rejects it (HTTP 401). Run this again with the right key." ;;
  *) echo "Saved to .env. Server check returned HTTP $code." ;;
esac
