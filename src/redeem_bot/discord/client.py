"""Discord REST API client with rate-limit aware retries."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from redeem_bot.discord.models import DiscordMessage

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
DEFAULT_PAGE_LIMIT = 100
DEFAULT_MAX_RETRIES = 5
DEFAULT_MAX_BACKOFF_SECONDS = 60.0


class DiscordApiError(RuntimeError):
    """Raised when the Discord API returns a non-retryable error."""


class DiscordRestClient:
    """Thin wrapper around Discord channel message endpoints."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DISCORD_API_BASE,
        timeout: float = 30.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": token,
                "User-Agent": "redeem-bot (REST fetcher, +https://example.test)",
            },
        )
        self._max_retries = max_retries
        self._max_backoff_seconds = max_backoff_seconds

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> DiscordRestClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_messages(
        self,
        channel_id: str,
        *,
        before: str | None = None,
        after: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> list[DiscordMessage]:
        params: dict[str, Any] = {"limit": min(max(limit, 1), DEFAULT_PAGE_LIMIT)}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after

        response = self._request("GET", f"/channels/{channel_id}/messages", params=params)
        payload = response.json()
        if not isinstance(payload, list):
            raise DiscordApiError(f"Unexpected Discord response for channel {channel_id}")

        return [DiscordMessage.from_api(item) for item in payload]

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        attempt = 0
        while True:
            response = self._client.request(method, path, **kwargs)
            if response.status_code == 429:
                attempt += 1
                if attempt > self._max_retries:
                    raise DiscordApiError("Discord rate limit exceeded after retries")
                delay = _retry_delay_seconds(response, attempt, self._max_backoff_seconds)
                logger.warning("Discord 429 on %s; sleeping %.2fs", path, delay)
                time.sleep(delay)
                continue

            if response.status_code >= 500 and attempt < self._max_retries:
                attempt += 1
                delay = min(2**attempt, self._max_backoff_seconds)
                logger.warning(
                    "Discord %s on %s; retry %d in %.2fs",
                    response.status_code,
                    path,
                    attempt,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.is_error:
                raise DiscordApiError(
                    f"Discord API error {response.status_code} for {path}: {response.text}"
                )

            _maybe_sleep_for_rate_limit(response)
            return response


def _retry_delay_seconds(
    response: httpx.Response,
    attempt: int,
    max_backoff_seconds: float,
) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(float(retry_after), max_backoff_seconds)
        except ValueError:
            pass
    return min(2**attempt, max_backoff_seconds)


def _maybe_sleep_for_rate_limit(response: httpx.Response) -> None:
    remaining = response.headers.get("X-RateLimit-Remaining")
    reset_after = response.headers.get("X-RateLimit-Reset-After")
    if remaining == "0" and reset_after is not None:
        try:
            delay = float(reset_after)
        except ValueError:
            return
        if delay > 0:
            logger.debug("Discord bucket empty; sleeping %.2fs", delay)
            time.sleep(delay)
