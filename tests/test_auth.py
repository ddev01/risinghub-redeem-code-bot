"""Tests for RisingHub login session handling."""

from __future__ import annotations

from pathlib import Path

import httpx

from redeem_bot.redeem.auth import LoginManager


def test_clear_session_removes_stale_cookie_file(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text('{"session": "stale"}', encoding="utf-8")

    client = httpx.Client()
    client.cookies.set("session", "stale")
    manager = LoginManager("https://example.test/", cookie_file, client=client)

    manager._clear_session()

    assert not cookie_file.exists()
    assert dict(client.cookies) == {}
