"""Discord webhook HTTP client and payload builders."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from redeem_bot.config import Settings, get_settings

logger = logging.getLogger(__name__)

FATAL_EMBED_COLOR = 15158332
SUCCESS_EMBED_COLOR = 3066993
DEBUG_EMBED_COLOR = 3447003
_WEBHOOK_TIMEOUT_SECONDS = 10.0
_MAX_FIELD_VALUE_LEN = 1024


def _utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _truncate(value: str, limit: int = _MAX_FIELD_VALUE_LEN) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _format_items(items: str | list[str]) -> str:
    if isinstance(items, str):
        return items
    return ", ".join(items)


def build_fatal_payload(command: str, error: Exception, *, timestamp: str | None = None) -> dict[str, Any]:
    """Build a Discord webhook payload that pings @everyone for fatal errors."""
    return {
        "content": "@everyone",
        "allowed_mentions": {"parse": ["everyone"]},
        "embeds": [
            {
                "title": "Redeem bot failed",
                "color": FATAL_EMBED_COLOR,
                "fields": [
                    {"name": "Command", "value": _truncate(command), "inline": True},
                    {"name": "Error", "value": _truncate(str(error)), "inline": False},
                    {"name": "Time (UTC)", "value": timestamp or _utc_now_label(), "inline": True},
                ],
            }
        ],
    }


def build_success_payload(
    code: str,
    account: str,
    hero: str,
    items: str | list[str],
    source: str,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a Discord webhook payload for successful redemptions (no ping)."""
    return {
        "embeds": [
            {
                "title": "Code redeemed",
                "color": SUCCESS_EMBED_COLOR,
                "fields": [
                    {"name": "Code", "value": _truncate(code), "inline": True},
                    {"name": "Account", "value": _truncate(account), "inline": True},
                    {"name": "Hero", "value": _truncate(hero), "inline": True},
                    {"name": "Items", "value": _truncate(_format_items(items)), "inline": False},
                    {"name": "Source", "value": _truncate(source), "inline": False},
                    {"name": "Time (UTC)", "value": timestamp or _utc_now_label(), "inline": True},
                ],
            }
        ],
    }


def build_discord_message_url(
    *,
    guild_id: str | None,
    channel_id: str | None,
    message_id: str | None,
) -> str | None:
    """Return a jump link when guild, channel, and message IDs are all known."""
    if not guild_id or not channel_id or not message_id:
        return None
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def build_code_debug_payload(
    *,
    code: str,
    author: str | None,
    channel_id: str | None,
    message_id: str | None,
    message_snippet: str | None,
    message_url: str | None,
    probe_summary: str,
    redemption_summary: str,
    skipped_reason: str | None,
    dry_run: bool,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Verbose pipeline trace for accuracy monitoring (no @everyone ping)."""
    link_value = message_url or "Set DISCORD_GUILD_ID for jump links"
    fields: list[dict[str, Any]] = [
        {"name": "Code", "value": _truncate(code), "inline": True},
        {"name": "Author", "value": _truncate(author or "unknown"), "inline": True},
        {"name": "Channel", "value": _truncate(channel_id or "—"), "inline": True},
        {"name": "Message", "value": _truncate(link_value), "inline": False},
        {"name": "Message text", "value": _truncate(message_snippet or "—"), "inline": False},
        {"name": "Probe", "value": _truncate(probe_summary), "inline": False},
        {"name": "Redemptions", "value": _truncate(redemption_summary), "inline": False},
    ]
    if skipped_reason:
        fields.append({"name": "Skipped", "value": _truncate(skipped_reason), "inline": True})
    if dry_run:
        fields.append({"name": "Mode", "value": "dry-run", "inline": True})
    fields.append({"name": "Time (UTC)", "value": timestamp or _utc_now_label(), "inline": True})

    return {
        "embeds": [
            {
                "title": "Code pipeline (debug)",
                "color": DEBUG_EMBED_COLOR,
                "fields": fields,
            }
        ],
    }


def post_webhook(payload: dict[str, Any], *, settings: Settings | None = None) -> None:
    """POST payload to DISCORD_WEBHOOK_URL; log and skip when unset or on HTTP failure."""
    resolved = settings or get_settings()
    url = resolved.discord_webhook_url
    if not url:
        logger.debug("DISCORD_WEBHOOK_URL unset; skipping webhook notification")
        return

    try:
        response = httpx.post(url, json=payload, timeout=_WEBHOOK_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to send Discord webhook: %s", exc)
