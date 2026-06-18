#!/usr/bin/env bash
# Install or update the redeem-bot cron line for the current user.
# Usage: ./deploy/install-cron.sh
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "$0")/lib.sh"
REMOTE_PATH="${REMOTE_PATH:-$HOME/risinghub-redeem-code-bot}"
MARKER="# redeem-bot cron"
CRON_LINE="0 */2 * * * cd ${REMOTE_PATH} && .venv/bin/redeem-bot run >> data/run.log 2>&1 ${MARKER}"

tmp="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$MARKER" > "$tmp" || true
printf '%s\n' "$CRON_LINE" >> "$tmp"
crontab "$tmp"
rm -f "$tmp"

echo "Installed cron:"
crontab -l | grep "$MARKER"
