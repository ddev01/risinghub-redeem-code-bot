# RisingHub Redeem Bot

Cron-driven CLI that fetches promo codes from Discord channels, extracts candidates with heuristics, then redeems on every hero for every configured account.

> **Personal use only.** Discord selfbots violate Discord's Terms of Service. Use at your own risk.

## Features

- **REST-only Discord fetch** — no gateway; short-lived cron runs
- **Fixture-tunable extraction** — `extract test` for playback before live redemption
- **Redeem everywhere** — every hero on every account; seasonal codes may redeem per hero and already-redeemed responses are expected
- **SQLite state** — channel cursors, seen codes, redemption attempts, run log
- **Webhook alerts** — `@everyone` on fatal errors; success embeds without ping; optional debug traces

## Setup

1. Python 3.10+
2. Install the package (editable dev install):

   ```bash
   pip install -e ".[dev]"
   ```

3. Copy env and accounts templates:

   ```bash
   cp .env.example .env
   cp config/accounts.example.json config/accounts.json
   ```

4. Edit `.env` with your RisingHub base URL, Discord token, channel IDs, and webhook URL.
5. Edit `config/accounts.json` with account credentials and hero priorities.

## Configuration

| Variable | Purpose |
| -------- | ------- |
| `RISINGHUB_BASE_URL` | RisingHub site root (trailing slash optional) |
| `DISCORD_USER_TOKEN` | User token for REST message fetch |
| `DISCORD_CHANNEL_IDS` | Comma-separated channel IDs to watch |
| `DISCORD_FETCH_SINCE` | Default lower bound for first fetch |
| `DISCORD_WEBHOOK_URL` | Webhook for fatal errors and successes |
| `DISCORD_WEBHOOK_DEBUG` | When `true`, post verbose pipeline traces (source msg, probe, per-account results) to the same webhook |
| `DISCORD_GUILD_ID` | Server ID for Discord message jump links in debug traces |
| `ACCOUNTS_FILE` | Path to accounts JSON (default `config/accounts.json`) |
| `DATA_DIR` | Runtime data root (default `data/`) |

Accounts JSON shape:

```json
{
  "accounts": [
    {
      "username": "test_user_01",
      "password": "CHANGE_ME",
      "priority_heroes": [
        "test_hero_roy_soldier",
        "test_hero_roy_gunner",
        "test_hero_nat_soldier",
        "test_hero_nat_gunner",
        "test_hero_roy_mando",
        "test_hero_nat_mando"
      ],
      "heroes": {}
    }
  ],
  "settings": {
    "rate_limit_delay": 2.0,
    "account_delay_multiplier": 2.0
  }
}
```

`priority_heroes` is an ordered list of hero names from your RisingHub profile. Those heroes are tried first; any other heroes on the profile are tried afterward in random order. Leave the list empty (`[]`) to try every hero in random order. Old `priority_nat_hero` / `priority_roy_hero` / `priority_faction` fields are still accepted and migrated automatically.

## CLI commands

| Command | Description |
| ------- | ----------- |
| `redeem-bot fetch [--since DATE] [--channel-id ID]` | Pull Discord messages into JSONL cache |
| `redeem-bot extract test [--since DATE] [--from-cache]` | Print extraction report (no redemption) |
| `redeem-bot redeem --code CODE[,CODE...] [--dry-run] [--force]` | Manually redeem one or more codes |
| `redeem-bot run [--dry-run] [--from-cache] [--since DATE]` | Full pipeline |
| `redeem-bot codes skip-backlog [--since DATE] [--dry-run]` | Mark pending cache codes as tried (skip old backlog) |
| `redeem-bot status` | Cursors, pending codes, last run |

### Examples

```bash
# Tune extraction from cached messages
redeem-bot extract test --from-cache --since 2025-03-01
# Also writes data/reports/extract-codes-YYYY-MM-DD.txt (CODE<TAB>author per line)

# Dry-run full pipeline (no HTTP redemption)
redeem-bot run --dry-run --from-cache --since 2025-03-01

# Live cron run (fetch + redeem)
redeem-bot run

# Redeem several codes in one go
redeem-bot redeem --force --code SPRING-2025-RH-NAT,RHWC-EVENT-2026-NAT,RHWC-EVENT-2026-ROY

# After manual testing: skip the old Discord backlog so cron only tries new codes
redeem-bot codes skip-backlog --dry-run   # preview
redeem-bot codes skip-backlog
```

## Cron deployment

Run every 2 hours on a small VPS:

```cron
0 */2 * * * cd /path/to/risinghub-redeem-code-bot && .venv/bin/redeem-bot run >> data/run.log 2>&1
```

Each invocation fetches new messages, processes untried codes only, and exits. Seasonal codes reposted in Discord (e.g. weekly dotw bulletins) are tried once; later mentions are skipped automatically via `seen_codes` in SQLite.

## Data layout

```
data/
├── cache/messages/{channel_id}.jsonl
├── state.sqlite
├── sessions/{username}/cookies.json
└── reports/extract-{date}.json
```

## Tests

```bash
pytest
```

## Deployment

Deploy from your laptop to the VPS over SSH (`SERVER=server` by default):

```bash
./deploy/check-env.sh    # validate .env + accounts.json locally
./deploy/deploy.sh       # rsync code, install venv on server, run smoke checks
```

Useful overrides:

```bash
SKIP_TESTS=1 ./deploy/deploy.sh
SERVER=server REMOTE_PATH='~/risinghub-redeem-code-bot' ./deploy/deploy.sh
```

**What deploy preserves:** server `data/` (SQLite, Discord cache, sessions) is never deleted.

**What deploy copies separately:** `.env` and `config/accounts.json` (gitignored secrets).

**Production readiness checklist:**

1. Local: `pytest` passes
2. Local: `./deploy/check-env.sh` passes (no `CHANGE_ME` / `example.test` placeholders)
3. Server: `./deploy/smoke.sh` passes after deploy
4. Server: `redeem-bot fetch` then `redeem-bot extract test --from-cache --since 2025-08-01` looks sane
5. Server: `redeem-bot run --dry-run --from-cache` completes without errors
6. Server: manual `redeem-bot redeem --code SOME-KNOWN-CODE --dry-run` if you want to verify hero order
7. Enable cron when satisfied: `ssh server 'cd ~/risinghub-redeem-code-bot && ./deploy/install-cron.sh'`

**Repo `old/` folder:** legacy pre-rewrite code; not deployed (rsync excludes it). Safe to delete locally once you no longer need it for reference.

**`Risinghub-claw-bot` on the server:** separate older browser bot; remove manually when you have fully switched to this CLI bot.

## License

Personal use only. Not for commercial redistribution.
