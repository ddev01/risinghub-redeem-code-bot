"""Shared datetime parsing for CLI flags and Discord timestamps."""

from __future__ import annotations

from datetime import datetime, timezone

from redeem_bot.config import Settings


def parse_datetime(value: str) -> datetime:
    """Parse an ISO date or datetime string into UTC."""
    normalized = value.replace("Z", "+00:00")
    if "T" not in normalized:
        normalized = f"{normalized}T00:00:00+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_since(since: str | None, settings: Settings) -> datetime:
    """Parse --since or fall back to env/default lower bound."""
    raw = since or settings.discord_fetch_since or "2025-01-01"
    return parse_datetime(raw)
