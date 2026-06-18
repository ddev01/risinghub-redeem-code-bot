#!/usr/bin/env bash
# Validate required .env and accounts before deploy.
# Usage: ./deploy/check-env.sh
set -euo pipefail

# shellcheck source=deploy/lib.sh
source "$(dirname "$0")/lib.sh"
ROOT="$(deploy_root)"
cd "$ROOT"

source_dotenv "$ROOT"

required_vars=(
  RISINGHUB_BASE_URL
  DISCORD_USER_TOKEN
  DISCORD_CHANNEL_IDS
)

for var in "${required_vars[@]}"; do
  value="${!var:-}"
  if is_placeholder "$value"; then
    echo "error: ${var} is missing or still a placeholder in .env" >&2
    exit 1
  fi
done

if [[ ! -f "${ROOT}/config/accounts.json" ]]; then
  echo "error: config/accounts.json missing — copy config/accounts.example.json" >&2
  exit 1
fi

PYTHON="$(deploy_local_python "$ROOT")"
"$PYTHON" - <<'PY'
import json
import sys
from pathlib import Path

accounts_path = Path("config/accounts.json")
data = json.loads(accounts_path.read_text(encoding="utf-8"))
accounts = data.get("accounts") or []
if not accounts:
    sys.exit("error: config/accounts.json has no accounts")

for index, account in enumerate(accounts, start=1):
    username = (account.get("username") or "").strip()
    password = account.get("password") or ""
    if not username or "CHANGE_ME" in password or password in {"", "x", "secret"}:
        sys.exit(f"error: account #{index} in accounts.json looks incomplete")
    heroes = account.get("priority_heroes") or []
    if heroes and all("test_hero" in hero for hero in heroes):
        print(f"warning: account {username} still uses example hero names", file=sys.stderr)

print(f"ok: {len(accounts)} account(s) configured")
PY

echo "==> .env and accounts.json look deployable"
