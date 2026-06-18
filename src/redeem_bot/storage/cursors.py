"""Per-channel Discord message cursor persistence."""

from __future__ import annotations

from pathlib import Path

from redeem_bot.storage.db import connect


def get_channel_cursor(db_path: Path, channel_id: str) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT last_message_id FROM channel_cursors WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        if row is None:
            return None
        return row["last_message_id"]


def set_channel_cursor(db_path: Path, channel_id: str, message_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO channel_cursors (channel_id, last_message_id, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(channel_id) DO UPDATE SET
                last_message_id = excluded.last_message_id,
                updated_at = excluded.updated_at
            """,
            (channel_id, message_id),
        )
