"""Tried-code tracking in SQLite (dedupe reposted seasonal codes)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from redeem_bot.extract.models import ExtractedCode
from redeem_bot.storage.db import connect

# Outcomes stored when a code has been attempted at least once (live run).
OUTCOME_PROBE_FAILED = "probe_failed"
OUTCOME_ALREADY_REDEEMED = "already_redeemed"
OUTCOME_REDEEMED = "redeemed"
OUTCOME_SKIPPED_BACKLOG = "skipped_backlog"
OUTCOME_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TriedCode:
    normalized_code: str
    outcome: str
    first_seen_at: str
    attempted_at: str | None
    source_message_id: str | None
    source_channel_id: str | None


@dataclass(frozen=True)
class TriedCodeInput:
    normalized_code: str
    source_message_id: str | None = None
    source_channel_id: str | None = None


def filter_untried(db_path: Path, codes: list[ExtractedCode]) -> list[ExtractedCode]:
    """Return codes not yet tried, preserving first occurrence order."""
    if not codes:
        return []

    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in codes)
        normalized = [code.normalized_code.upper() for code in codes]
        rows = conn.execute(
            f"SELECT normalized_code FROM seen_codes WHERE normalized_code IN ({placeholders})",
            normalized,
        ).fetchall()
        already_tried = {row["normalized_code"] for row in rows}

    seen_in_batch: set[str] = set()
    untried: list[ExtractedCode] = []
    for code in codes:
        key = code.normalized_code.upper()
        if key in seen_in_batch or key in already_tried:
            continue
        seen_in_batch.add(key)
        untried.append(code)
    return untried


def is_tried(db_path: Path, normalized_code: str) -> bool:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_codes WHERE normalized_code = ?",
            (normalized_code.upper(),),
        ).fetchone()
    return row is not None


def get_tried_code(db_path: Path, normalized_code: str) -> TriedCode | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT normalized_code, outcome, first_seen_at, attempted_at,
                   source_message_id, source_channel_id
            FROM seen_codes
            WHERE normalized_code = ?
            """,
            (normalized_code.upper(),),
        ).fetchone()
    if row is None:
        return None
    return TriedCode(
        normalized_code=row["normalized_code"],
        outcome=row["outcome"] or OUTCOME_UNKNOWN,
        first_seen_at=row["first_seen_at"],
        attempted_at=row["attempted_at"],
        source_message_id=row["source_message_id"],
        source_channel_id=row["source_channel_id"],
    )


def get_tried_outcomes(db_path: Path, normalized_codes: list[str]) -> dict[str, str]:
    if not normalized_codes:
        return {}
    keys = [code.upper() for code in normalized_codes]
    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"""
            SELECT normalized_code, outcome
            FROM seen_codes
            WHERE normalized_code IN ({placeholders})
            """,
            keys,
        ).fetchall()
    return {
        row["normalized_code"]: row["outcome"] or OUTCOME_UNKNOWN
        for row in rows
    }


def mark_tried(
    db_path: Path,
    code: TriedCodeInput,
    outcome: str,
    *,
    dry_run: bool = False,
) -> None:
    """Record that a code was attempted. Skipped during dry-run."""
    if dry_run:
        return
    mark_tried_batch(db_path, [code], outcome)


def mark_tried_batch(
    db_path: Path,
    codes: list[TriedCodeInput],
    outcome: str,
    *,
    dry_run: bool = False,
) -> int:
    """Record many codes at once. Returns number marked (0 when dry_run)."""
    if dry_run or not codes:
        return 0

    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO seen_codes (
                normalized_code, source_message_id, source_channel_id, outcome, attempted_at
            )
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(normalized_code) DO UPDATE SET
                outcome = excluded.outcome,
                attempted_at = datetime('now'),
                source_message_id = COALESCE(seen_codes.source_message_id, excluded.source_message_id),
                source_channel_id = COALESCE(seen_codes.source_channel_id, excluded.source_channel_id)
            """,
            [
                (
                    code.normalized_code.upper(),
                    code.source_message_id,
                    code.source_channel_id,
                    outcome,
                )
                for code in codes
            ],
        )
    return len(codes)


def count_tried(db_path: Path) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM seen_codes").fetchone()
    return int(row["n"])
