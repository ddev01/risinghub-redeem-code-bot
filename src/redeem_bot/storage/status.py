"""Read-only status queries for CLI and ops."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from redeem_bot.storage.db import connect


@dataclass(frozen=True)
class ChannelCursorRow:
    channel_id: str
    last_message_id: str | None
    updated_at: str


@dataclass(frozen=True)
class OutcomeCount:
    outcome: str
    count: int


@dataclass(frozen=True)
class LastRunRow:
    command: str
    started_at: str
    finished_at: str | None
    status: str
    summary: str | None


def count_tried_codes(db_path: Path) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM seen_codes").fetchone()
    return int(row["n"])


def tried_outcome_counts(db_path: Path) -> list[OutcomeCount]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(outcome, 'unknown') AS outcome, COUNT(*) AS n
            FROM seen_codes
            GROUP BY COALESCE(outcome, 'unknown')
            ORDER BY outcome
            """
        ).fetchall()
    return [OutcomeCount(outcome=row["outcome"], count=int(row["n"])) for row in rows]


def count_successful_redemptions(db_path: Path) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM successful_redemptions").fetchone()
    return int(row["n"])


def channel_cursors(db_path: Path) -> list[ChannelCursorRow]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT channel_id, last_message_id, updated_at FROM channel_cursors ORDER BY channel_id"
        ).fetchall()
    return [
        ChannelCursorRow(
            channel_id=row["channel_id"],
            last_message_id=row["last_message_id"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def last_run(db_path: Path) -> LastRunRow | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT command, started_at, finished_at, status, summary
            FROM run_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return LastRunRow(
        command=row["command"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        status=row["status"],
        summary=row["summary"],
    )
