"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from redeem_bot.discord.models import DiscordAuthor, DiscordMessage, parse_timestamp
from redeem_bot.storage.cache import append_messages


def seed_cache_from_messages(
    cache_dir: Path,
    channel_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Write fixture-style message dicts to JSONL cache."""
    discord_messages: list[DiscordMessage] = []
    for message in messages:
        author_raw = message.get("author", {})
        discord_messages.append(
            DiscordMessage(
                id=str(message["id"]),
                channel_id=str(message.get("channel_id", channel_id)),
                content=str(message.get("content", "")),
                timestamp=parse_timestamp(str(message["timestamp"])),
                author=DiscordAuthor(
                    id=str(author_raw.get("id", "0")),
                    username=str(author_raw.get("username", "unknown")),
                ),
            )
        )
    append_messages(cache_dir, channel_id, discord_messages)
