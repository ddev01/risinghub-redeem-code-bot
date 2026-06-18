"""JSONL message cache read/write helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from redeem_bot.discord.models import DiscordMessage, parse_timestamp


def cache_path_for_channel(cache_dir: Path, channel_id: str) -> Path:
    return cache_dir / f"{channel_id}.jsonl"


def append_messages(
    cache_dir: Path,
    channel_id: str,
    messages: list[DiscordMessage],
) -> int:
    """Append messages to the channel JSONL cache. Returns lines written."""
    if not messages:
        return 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path_for_channel(cache_dir, channel_id)
    with path.open("a", encoding="utf-8") as handle:
        for message in messages:
            handle.write(json.dumps(message.to_cache_dict(), ensure_ascii=False))
            handle.write("\n")
    return len(messages)


def load_cached_messages(
    cache_dir: Path,
    channel_id: str,
    since: datetime,
) -> list[DiscordMessage]:
    """Load cached messages for a channel with timestamp >= since."""
    path = cache_path_for_channel(cache_dir, channel_id)
    if not path.exists():
        return []

    messages: list[DiscordMessage] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            message = DiscordMessage.from_cache_dict(raw)
            if message.timestamp >= since:
                messages.append(message)

    messages.sort(key=lambda item: item.timestamp)
    return messages
