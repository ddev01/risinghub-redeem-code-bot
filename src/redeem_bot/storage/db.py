"""SQLite connection helpers and schema initialization."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from redeem_bot.storage.schema import CREATE_TABLES_SQL, SCHEMA_VERSION


def init_db(db_path: Path) -> None:
    """Create parent directories and apply schema if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(CREATE_TABLES_SQL)
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        _apply_migrations(conn)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    version = int(row["version"]) if row is not None else SCHEMA_VERSION

    if version < 2:
        columns = _table_columns(conn, "seen_codes")
        if "outcome" not in columns:
            conn.execute("ALTER TABLE seen_codes ADD COLUMN outcome TEXT")
        if "attempted_at" not in columns:
            conn.execute("ALTER TABLE seen_codes ADD COLUMN attempted_at TEXT")
        conn.execute(
            """
            UPDATE seen_codes
            SET outcome = ?, attempted_at = COALESCE(attempted_at, first_seen_at)
            WHERE outcome IS NULL
            """,
            ("unknown",),
        )
        conn.execute("UPDATE schema_version SET version = 2")


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
