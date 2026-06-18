"""Pytest hooks shared across the test suite."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def block_real_discord_webhooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never send live Discord webhook HTTP during tests."""

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "")
    monkeypatch.setenv("DISCORD_WEBHOOK_DEBUG", "false")

    def _blocked_post(*_args, **_kwargs) -> MagicMock:
        response = MagicMock(status_code=204)
        response.raise_for_status = MagicMock()
        return response

    monkeypatch.setattr("redeem_bot.notify.webhook.httpx.post", _blocked_post)
