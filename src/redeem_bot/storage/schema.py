"""SQLite schema definitions for bot runtime state."""

SCHEMA_VERSION = 2

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_cursors (
    channel_id TEXT PRIMARY KEY,
    last_message_id TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS seen_codes (
    normalized_code TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_message_id TEXT,
    source_channel_id TEXT,
    outcome TEXT,
    attempted_at TEXT
);

CREATE TABLE IF NOT EXISTS redemption_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_code TEXT NOT NULL,
    account_username TEXT NOT NULL,
    hero_name TEXT,
    hero_id TEXT,
    outcome TEXT NOT NULL,
    detail TEXT,
    attempted_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (normalized_code, account_username, hero_name)
);

CREATE TABLE IF NOT EXISTS successful_redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_code TEXT NOT NULL UNIQUE,
    account_username TEXT NOT NULL,
    hero_name TEXT NOT NULL,
    hero_id TEXT,
    items_json TEXT,
    source_message_id TEXT,
    source_channel_id TEXT,
    redeemed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    summary TEXT
);
"""
