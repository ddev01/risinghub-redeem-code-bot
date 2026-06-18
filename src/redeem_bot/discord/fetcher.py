"""
Discord REST message fetcher (no gateway).

Using a user token against the Discord REST API violates Discord's Terms of
Service. This module is intended for personal, self-hosted automation only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from redeem_bot.config import Settings, get_settings
from redeem_bot.discord.client import DEFAULT_PAGE_LIMIT, DiscordRestClient
from redeem_bot.discord.cursors import get_channel_cursor, set_channel_cursor
from redeem_bot.discord.models import DiscordMessage, FetchResult, parse_timestamp
from redeem_bot.storage.cache import append_messages, load_cached_messages as _load_cached_messages
from redeem_bot.storage.db import init_db

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES_PER_RUN = 50


def fetch_channel(
    channel_id: str,
    since: datetime | None = None,
    from_cursor: bool = True,
    *,
    settings: Settings | None = None,
    client: DiscordRestClient | None = None,
    max_pages: int = DEFAULT_MAX_PAGES_PER_RUN,
) -> FetchResult:
    """Fetch channel messages via REST, append to JSONL cache, and update cursor."""
    cfg = settings or get_settings()
    cfg.ensure_data_dirs()
    init_db(cfg.state_db_path)

    cursor_before = get_channel_cursor(cfg.state_db_path, channel_id)
    lower_bound = _resolve_lower_bound(cfg, since, from_cursor, cursor_before)

    owns_client = client is None
    api_client = client or _build_client(cfg)
    try:
        if from_cursor and cursor_before and since is None:
            raw_messages, pages_fetched, stopped_reason = _fetch_after_cursor(
                api_client,
                channel_id,
                cursor_before,
                max_pages=max_pages,
            )
        else:
            raw_messages, pages_fetched, stopped_reason = _fetch_backward_since(
                api_client,
                channel_id,
                lower_bound,
                max_pages=max_pages,
            )
    finally:
        if owns_client:
            api_client.close()

    new_messages = _dedupe_against_cache(cfg.cache_dir, channel_id, raw_messages)
    cached_count = append_messages(cfg.cache_dir, channel_id, new_messages)

    cursor_after = cursor_before
    if new_messages:
        newest = max(new_messages, key=lambda item: int(item.id))
        set_channel_cursor(cfg.state_db_path, channel_id, newest.id)
        cursor_after = newest.id
    elif raw_messages and (not from_cursor or since is not None):
        newest = max(raw_messages, key=lambda item: int(item.id))
        if cursor_before is None or int(newest.id) > int(cursor_before):
            set_channel_cursor(cfg.state_db_path, channel_id, newest.id)
            cursor_after = newest.id

    return FetchResult(
        channel_id=channel_id,
        messages_fetched=len(raw_messages),
        messages_cached=cached_count,
        pages_fetched=pages_fetched,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
        stopped_reason=stopped_reason,
    )


def load_cached_messages(
    channel_id: str,
    since: datetime,
    *,
    settings: Settings | None = None,
) -> list[DiscordMessage]:
    """Load cached messages for a channel with timestamp >= since."""
    cfg = settings or get_settings()
    return _load_cached_messages(cfg.cache_dir, channel_id, since)


def fetch_all_channels(
    since: datetime | None = None,
    from_cursor: bool = True,
    *,
    channel_ids: list[str] | None = None,
    settings: Settings | None = None,
    client: DiscordRestClient | None = None,
    max_pages: int = DEFAULT_MAX_PAGES_PER_RUN,
) -> list[FetchResult]:
    """Fetch all configured channels (or an explicit subset)."""
    cfg = settings or get_settings()
    targets = channel_ids or cfg.channel_id_list
    if not targets:
        raise ValueError("No Discord channel IDs configured")

    results: list[FetchResult] = []
    owns_client = client is None
    api_client = client or _build_client(cfg)
    try:
        for channel_id in targets:
            results.append(
                fetch_channel(
                    channel_id,
                    since=since,
                    from_cursor=from_cursor,
                    settings=cfg,
                    client=api_client,
                    max_pages=max_pages,
                )
            )
    finally:
        if owns_client:
            api_client.close()
    return results


def _build_client(cfg: Settings) -> DiscordRestClient:
    if not cfg.discord_user_token:
        raise ValueError("DISCORD_USER_TOKEN is required for Discord fetch")
    return DiscordRestClient(cfg.discord_user_token)


def _resolve_lower_bound(
    cfg: Settings,
    since: datetime | None,
    from_cursor: bool,
    cursor_before: str | None,
) -> datetime:
    if since is not None:
        return _ensure_utc(since)
    if from_cursor and cursor_before:
        return datetime.min.replace(tzinfo=timezone.utc)
    if cfg.discord_fetch_since:
        return _ensure_utc(parse_timestamp(cfg.discord_fetch_since))
    return datetime.min.replace(tzinfo=timezone.utc)


def _fetch_after_cursor(
    client: DiscordRestClient,
    channel_id: str,
    cursor_id: str,
    *,
    max_pages: int,
) -> tuple[list[DiscordMessage], int, str]:
    collected: list[DiscordMessage] = []
    pages = 0

    page = client.fetch_messages(channel_id, after=cursor_id)
    pages += 1
    if not page:
        return collected, pages, "no_new_messages"

    collected.extend(page)
    if len(page) < DEFAULT_PAGE_LIMIT:
        return collected, pages, "end_of_channel"

    before_id = min(page, key=lambda item: int(item.id)).id
    while pages < max_pages:
        older_page = client.fetch_messages(channel_id, before=before_id)
        pages += 1
        if not older_page:
            return collected, pages, "end_of_channel"

        filtered = [message for message in older_page if int(message.id) > int(cursor_id)]
        collected.extend(filtered)

        oldest = min(older_page, key=lambda item: int(item.id))
        if int(oldest.id) <= int(cursor_id) or len(older_page) < DEFAULT_PAGE_LIMIT:
            return collected, pages, "end_of_channel"

        before_id = oldest.id

    return collected, pages, "max_pages_reached"


def _fetch_backward_since(
    client: DiscordRestClient,
    channel_id: str,
    since: datetime,
    *,
    max_pages: int,
) -> tuple[list[DiscordMessage], int, str]:
    collected: list[DiscordMessage] = []
    before_id: str | None = None
    pages = 0
    since_utc = _ensure_utc(since)

    while pages < max_pages:
        page = client.fetch_messages(channel_id, before=before_id)
        pages += 1
        if not page:
            return collected, pages, "end_of_channel"

        in_range = [message for message in page if _ensure_utc(message.timestamp) >= since_utc]
        collected.extend(in_range)

        oldest = min(page, key=lambda item: int(item.id))
        if _ensure_utc(oldest.timestamp) < since_utc:
            return collected, pages, "reached_since_bound"

        before_id = oldest.id

    return collected, pages, "max_pages_reached"


def _dedupe_against_cache(
    cache_dir: Path,
    channel_id: str,
    messages: list[DiscordMessage],
) -> list[DiscordMessage]:
    if not messages:
        return []

    earliest = min(messages, key=lambda item: item.timestamp)
    existing = _load_cached_messages(cache_dir, channel_id, earliest.timestamp)
    seen_ids = {message.id for message in existing}
    return [message for message in messages if message.id not in seen_ids]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
