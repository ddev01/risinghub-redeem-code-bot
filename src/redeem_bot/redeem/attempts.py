"""Persist redemption attempts and successes to SQLite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from redeem_bot.storage.db import connect, init_db


def ensure_db(db_path: Path) -> None:
    init_db(db_path)


def record_attempt(
    db_path: Path,
    normalized_code: str,
    account_username: str,
    hero_name: str | None,
    hero_id: str | None,
    outcome: str,
    detail: str | None = None,
) -> None:
    ensure_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO redemption_attempts (
                normalized_code, account_username, hero_name, hero_id, outcome, detail
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_code, account_username, hero_name) DO UPDATE SET
                hero_id = excluded.hero_id,
                outcome = excluded.outcome,
                detail = excluded.detail,
                attempted_at = datetime('now')
            """,
            (
                normalized_code,
                account_username,
                hero_name,
                hero_id,
                outcome,
                detail,
            ),
        )


def record_success(
    db_path: Path,
    normalized_code: str,
    account_username: str,
    hero_name: str,
    hero_id: str | None,
    items: dict[str, Any],
    source_message_id: str | None = None,
    source_channel_id: str | None = None,
) -> None:
    ensure_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO successful_redemptions (
                normalized_code, account_username, hero_name, hero_id,
                items_json, source_message_id, source_channel_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_code) DO UPDATE SET
                account_username = excluded.account_username,
                hero_name = excluded.hero_name,
                hero_id = excluded.hero_id,
                items_json = excluded.items_json,
                redeemed_at = datetime('now')
            """,
            (
                normalized_code,
                account_username,
                hero_name,
                hero_id,
                json.dumps(items),
                source_message_id,
                source_channel_id,
            ),
        )
