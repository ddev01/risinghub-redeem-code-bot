"""Pipeline run log persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from redeem_bot.storage.db import connect


def start_run_log(db_path: Path, command: str) -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO run_log (command, started_at, status)
            VALUES (?, ?, 'running')
            """,
            (command, started_at),
        )
        return int(cursor.lastrowid)


def finish_run_log(
    db_path: Path,
    run_id: int,
    *,
    status: str,
    summary: str | None = None,
) -> None:
    finished_at = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE run_log
            SET finished_at = ?, status = ?, summary = ?
            WHERE id = ?
            """,
            (finished_at, status, summary, run_id),
        )
