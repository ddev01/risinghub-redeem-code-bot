#!/usr/bin/env bash
# Deploy from local machine to VPS via SSH.
#
# Usage:
#   ./deploy/deploy.sh
#   SKIP_TESTS=1 ./deploy/deploy.sh
#   SERVER=server REMOTE_PATH='~/risinghub-redeem-code-bot' ./deploy/deploy.sh
#
# Preserves server data/ (SQLite, cache, sessions). Copies .env and
# config/accounts.json separately because they are gitignored locally.
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "$0")/lib.sh"
ROOT="$(deploy_root)"
cd "$ROOT"

SERVER="${SERVER:-server}"
REMOTE_PATH="${REMOTE_PATH:-~/risinghub-redeem-code-bot}"
SKIP_TESTS="${SKIP_TESTS:-0}"
RUN_SMOKE="${RUN_SMOKE:-1}"

echo "==> Validate local config"
"$(dirname "$0")/check-env.sh"

if [[ "$SKIP_TESTS" != "1" ]]; then
  echo "==> Run tests"
  PYTHON="$(deploy_local_python "$ROOT")"
  "$PYTHON" -m pytest -q
fi

echo "==> Sync code to ${SERVER}:${REMOTE_PATH}"
ssh "$SERVER" "mkdir -p ${REMOTE_PATH}/data/cache/messages ${REMOTE_PATH}/data/reports ${REMOTE_PATH}/data/sessions ${REMOTE_PATH}/config"
RSYNC_ARGS=(-az --delete
  --exclude '.venv/'
  --exclude 'data/'
  --exclude '.env'
  --exclude '.git/'
  --exclude 'config/accounts.json'
  --exclude 'old/'
  --exclude '__pycache__/'
  --exclude '.pytest_cache/'
  --exclude '.cursor/'
  --exclude '.env.local'
)
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY_RUN: would rsync to ${SERVER}:${REMOTE_PATH}"
  rsync -n "${RSYNC_ARGS[@]}" ./ "${SERVER}:${REMOTE_PATH}/"
else
  rsync "${RSYNC_ARGS[@]}" ./ "${SERVER}:${REMOTE_PATH}/"
fi

scp "${ROOT}/.env" "${SERVER}:${REMOTE_PATH}/.env"
scp "${ROOT}/config/accounts.json" "${SERVER}:${REMOTE_PATH}/config/accounts.json"

echo "==> Install on server"
ssh "$SERVER" bash -s <<EOF
set -euo pipefail
cd ${REMOTE_PATH}
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -e .
mkdir -p data/cache/messages data/reports data/sessions
chmod +x deploy/*.sh
EOF

if [[ "$RUN_SMOKE" == "1" ]]; then
  echo "==> Smoke checks on server"
  ssh "$SERVER" "cd ${REMOTE_PATH} && ./deploy/smoke.sh"
fi

cat <<EOF

Deployed to ${SERVER}:${REMOTE_PATH}

Next steps on the server:
  ssh ${SERVER}
  cd ${REMOTE_PATH}
  ./deploy/smoke.sh                 # re-run checks any time
  .venv/bin/redeem-bot fetch        # first-time Discord cache
  .venv/bin/redeem-bot extract test --from-cache --since 2025-08-01
  .venv/bin/redeem-bot run --dry-run --from-cache
  .venv/bin/redeem-bot run          # live cron-style run

Enable cron (once you are happy with dry-runs):
  ssh ${SERVER} 'cd ${REMOTE_PATH} && ./deploy/install-cron.sh'

The legacy Risinghub-claw-bot directory is separate; remove it manually when
you no longer need the old browser bot. The repo old/ folder is not deployed.
EOF
