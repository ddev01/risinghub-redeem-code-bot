"""Load Discord messages from cache or via the shared REST fetcher."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from redeem_bot.config import Settings
from redeem_bot.discord.fetcher import fetch_all_channels, fetch_channel
from redeem_bot.discord.models import DiscordMessage
from redeem_bot.storage.cache import load_cached_messages


def _message_to_dict(message: DiscordMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "channel_id": message.channel_id,
        "timestamp": message.timestamp.isoformat(),
        "author": {"username": message.author.username},
        "content": message.content,
    }


def _channel_ids(settings: Settings, channel_id: str | None) -> list[str]:
    channel_ids = [channel_id] if channel_id else settings.channel_id_list
    if not channel_ids:
        raise ValueError(
            "Provide --channel-id or set DISCORD_CHANNEL_IDS in the environment."
        )
    return channel_ids


def _load_from_cache(
    settings: Settings,
    channel_ids: list[str],
    since: datetime,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for cid in channel_ids:
        cached = load_cached_messages(settings.cache_dir, cid, since)
        messages.extend(_message_to_dict(message) for message in cached)
    return messages


def load_messages(
    settings: Settings,
    *,
    since: datetime,
    channel_id: str | None,
    from_cache: bool,
    incremental_fetch: bool = False,
) -> list[dict[str, Any]]:
    """
    Return message dicts for extraction.

    When ``from_cache`` is False, fetches from Discord first:
    - ``incremental_fetch=True``: new messages since cursor (cron-style run).
    - otherwise: backfill from ``since`` with ``from_cursor=False``.
    """
    channel_ids = _channel_ids(settings, channel_id)

    if from_cache:
        return _load_from_cache(settings, channel_ids, since)

    if not settings.discord_user_token:
        raise ValueError(
            "DISCORD_USER_TOKEN is required when not using --from-cache."
        )

    if incremental_fetch:
        if channel_id:
            fetch_channel(channel_id, settings=settings)
        else:
            fetch_all_channels(settings=settings)
    elif channel_id:
        fetch_channel(
            channel_id,
            since=since,
            from_cursor=False,
            settings=settings,
        )
    else:
        fetch_all_channels(since=since, from_cursor=False, settings=settings)

    return _load_from_cache(settings, channel_ids, since)
