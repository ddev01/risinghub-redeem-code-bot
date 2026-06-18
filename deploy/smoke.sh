#!/usr/bin/env bash
# Post-deploy smoke checks on the VPS.
# Usage: ./deploy/smoke.sh
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "$0")/lib.sh"
ROOT="$(deploy_root)"
cd "$ROOT"

if [[ ! -x "${ROOT}/.venv/bin/redeem-bot" ]]; then
  echo "error: .venv/bin/redeem-bot not found — run deploy first" >&2
  exit 1
fi

BOT="${ROOT}/.venv/bin/redeem-bot"
PYTHON="${ROOT}/.venv/bin/python"

echo "==> Config load"
"$PYTHON" - <<'PY'
from redeem_bot.config import get_settings

settings = get_settings()
accounts = settings.load_accounts()
print(
    f"base_url={settings.risinghub_base_url} "
    f"channels={len(settings.channel_id_list)} "
    f"accounts={len(accounts.accounts)}"
)
PY

echo "==> CLI status"
"$BOT" status

if compgen -G "${ROOT}/data/cache/messages/*.jsonl" > /dev/null; then
  echo "==> Dry-run pipeline (cached messages)"
  "$BOT" run --dry-run --from-cache
else
  echo "==> Skip pipeline dry-run: no message cache yet"
  echo "    Run: redeem-bot fetch"
fi

echo "==> Smoke checks passed"
