"""Tests for Discord REST fetcher, JSONL cache, and cursors."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from redeem_bot.discord.client import DISCORD_API_BASE, DiscordRestClient
from redeem_bot.discord.fetcher import fetch_channel, load_cached_messages
from redeem_bot.discord.models import DiscordMessage
from redeem_bot.storage.cache import append_messages, load_cached_messages as cache_load
from redeem_bot.storage.db import init_db


CHANNEL_ID = "123456789012345678"
TOKEN = "test_token_value"


def _message(
    message_id: str,
    *,
    content: str = "hello",
    timestamp: str = "2025-06-01T12:00:00.000000+00:00",
    username: str = "test_user_01",
) -> dict:
    return {
        "id": message_id,
        "channel_id": CHANNEL_ID,
        "content": content,
        "timestamp": timestamp,
        "author": {"id": "987654321098765432", "username": username},
    }


def _settings(tmp_path: Path):
    from redeem_bot.config import Settings

    return Settings(
        DISCORD_USER_TOKEN=TOKEN,
        DISCORD_CHANNEL_IDS=CHANNEL_ID,
        DATA_DIR=tmp_path / "data",
    )


def _mock_client(handler) -> DiscordRestClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url=DISCORD_API_BASE)
    return DiscordRestClient(TOKEN, client=http_client)


def test_append_and_load_cached_messages(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    message = DiscordMessage.from_api(_message("1001", content="cached-msg"))
    append_messages(cache_dir, CHANNEL_ID, [message])

    since = datetime(2025, 1, 1, tzinfo=timezone.utc)
    loaded = cache_load(cache_dir, CHANNEL_ID, since)
    assert len(loaded) == 1
    assert loaded[0].content == "cached-msg"
    assert loaded[0].author.username == "test_user_01"


def test_load_cached_messages_filters_by_since(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    older = DiscordMessage.from_api(
        _message("1001", timestamp="2025-01-01T00:00:00.000000+00:00")
    )
    newer = DiscordMessage.from_api(
        _message("1002", timestamp="2025-06-01T00:00:00.000000+00:00")
    )
    append_messages(cache_dir, CHANNEL_ID, [older, newer])

    since = datetime(2025, 3, 1, tzinfo=timezone.utc)
    loaded = cache_load(cache_dir, CHANNEL_ID, since)
    assert [item.id for item in loaded] == ["1002"]


def test_fetch_channel_after_cursor(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    init_db(settings.state_db_path)

    from redeem_bot.discord.cursors import set_channel_cursor

    set_channel_cursor(settings.state_db_path, CHANNEL_ID, "1000")

    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params.get("after", request.url.params.get("before", "")))
        if request.url.params.get("after") == "1000":
            return httpx.Response(
                200,
                json=[
                    _message("1002", content="newest"),
                    _message("1001", content="older"),
                ],
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    client = _mock_client(handler)
    result = fetch_channel(
        CHANNEL_ID,
        from_cursor=True,
        settings=settings,
        client=client,
    )

    assert result.messages_fetched == 2
    assert result.messages_cached == 2
    assert result.cursor_after == "1002"
    assert result.stopped_reason == "end_of_channel"

    cache_file = settings.cache_dir / f"{CHANNEL_ID}.jsonl"
    lines = cache_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["content"] == "newest"


def test_fetch_channel_backward_since_overrides_cursor(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    init_db(settings.state_db_path)

    from redeem_bot.discord.cursors import set_channel_cursor

    set_channel_cursor(settings.state_db_path, CHANNEL_ID, "3000")

    def handler(request: httpx.Request) -> httpx.Response:
        before = request.url.params.get("before")
        if before is None:
            return httpx.Response(
                200,
                json=[
                    _message("3002", timestamp="2025-06-02T00:00:00.000000+00:00"),
                    _message("3001", timestamp="2025-06-01T00:00:00.000000+00:00"),
                ],
                request=request,
            )
        if before == "3001":
            return httpx.Response(
                200,
                json=[
                    _message("2001", timestamp="2025-05-01T00:00:00.000000+00:00"),
                ],
                request=request,
            )
        raise AssertionError(f"Unexpected before={before}")

    since = datetime(2025, 6, 1, tzinfo=timezone.utc)
    client = _mock_client(handler)
    result = fetch_channel(
        CHANNEL_ID,
        since=since,
        from_cursor=False,
        settings=settings,
        client=client,
    )

    assert result.messages_fetched == 2
    assert result.messages_cached == 2
    assert result.stopped_reason == "reached_since_bound"


def test_fetch_channel_dedupes_existing_cache(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    init_db(settings.state_db_path)
    settings.ensure_data_dirs()

    existing = DiscordMessage.from_api(_message("1001", content="already-there"))
    append_messages(settings.cache_dir, CHANNEL_ID, [existing])

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                200,
                json=[
                    _message("1002", content="fresh"),
                    _message("1001", content="duplicate"),
                ],
                request=request,
            )
        return httpx.Response(200, json=[], request=request)

    client = _mock_client(handler)
    result = fetch_channel(
        CHANNEL_ID,
        since=datetime(2025, 1, 1, tzinfo=timezone.utc),
        from_cursor=False,
        settings=settings,
        client=client,
    )

    assert result.messages_fetched == 2
    assert result.messages_cached == 1
    assert result.cursor_after == "1002"


def test_client_retries_on_rate_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("redeem_bot.discord.client.time.sleep", lambda s: sleeps.append(s))

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"}, request=request)
        return httpx.Response(200, json=[_message("1001")], request=request)

    client = _mock_client(handler)
    messages = client.fetch_messages(CHANNEL_ID, after="1000")
    client.close()

    assert len(messages) == 1
    assert calls["count"] == 2
    assert sleeps == [1.5]


def test_load_cached_messages_public_api(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ensure_data_dirs()
    message = DiscordMessage.from_api(_message("1001"))
    append_messages(settings.cache_dir, CHANNEL_ID, [message])

    since = datetime(2025, 1, 1, tzinfo=timezone.utc)
    loaded = load_cached_messages(CHANNEL_ID, since, settings=settings)
    assert len(loaded) == 1
