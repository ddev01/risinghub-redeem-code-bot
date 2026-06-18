#!/usr/bin/env bash
# Shared helpers for deploy scripts (sourced, not executed).

deploy_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

source_dotenv() {
  local root="${1:-}"
  local env_file="${2:-${root}/.env}"
  if [[ ! -f "$env_file" ]]; then
    echo "error: missing .env — copy .env.example to .env and set required values." >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
}

deploy_local_python() {
  local root="$1"
  if [[ -x "${root}/.venv/bin/python" ]]; then
    printf '%s\n' "${root}/.venv/bin/python"
  else
    command -v python3
  fi
}

is_placeholder() {
  local value="$1"
  [[ -z "$value" ]] && return 0
  [[ "$value" == *CHANGE_ME* ]] && return 0
  [[ "$value" == "https://example.test/" ]] && return 0
  [[ "$value" == "https://example.test" ]] && return 0
  return 1
}
