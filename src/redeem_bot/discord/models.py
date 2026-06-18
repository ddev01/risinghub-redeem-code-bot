"""Discord message and fetch result models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DiscordAuthor:
    id: str
    username: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> DiscordAuthor:
        return cls(id=str(raw["id"]), username=str(raw.get("username", "unknown")))


@dataclass(frozen=True)
class DiscordMessage:
    id: str
    channel_id: str
    content: str
    timestamp: datetime
    author: DiscordAuthor

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> DiscordMessage:
        return cls(
            id=str(raw["id"]),
            channel_id=str(raw["channel_id"]),
            content=str(raw.get("content", "")),
            timestamp=parse_timestamp(str(raw["timestamp"])),
            author=DiscordAuthor.from_api(raw.get("author", {})),
        )

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "author": {"id": self.author.id, "username": self.author.username},
        }

    @classmethod
    def from_cache_dict(cls, raw: dict[str, Any]) -> DiscordMessage:
        author_raw = raw.get("author", {})
        return cls(
            id=str(raw["id"]),
            channel_id=str(raw["channel_id"]),
            content=str(raw.get("content", "")),
            timestamp=parse_timestamp(str(raw["timestamp"])),
            author=DiscordAuthor(
                id=str(author_raw.get("id", "0")),
                username=str(author_raw.get("username", "unknown")),
            ),
        )


@dataclass(frozen=True)
class FetchResult:
    channel_id: str
    messages_fetched: int
    messages_cached: int
    pages_fetched: int
    cursor_before: str | None
    cursor_after: str | None
    stopped_reason: str


def parse_timestamp(value: str) -> datetime:
    from redeem_bot.timeparse import parse_datetime

    return parse_datetime(value)
