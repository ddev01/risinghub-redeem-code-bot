#!/usr/bin/env bash
# One-off: mark all pending cache codes as tried (same set `run` would redeem).
# Usage: ./deploy/skip-backlog.sh [--dry-run] [--since DATE]
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "$0")/lib.sh"
ROOT="$(deploy_root)"
cd "$ROOT"

if [[ ! -x .venv/bin/redeem-bot ]]; then
  echo "error: .venv/bin/redeem-bot not found" >&2
  exit 1
fi

exec .venv/bin/redeem-bot codes skip-backlog "$@"
