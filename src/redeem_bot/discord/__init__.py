"""
Discord REST message fetcher (no gateway).

Using a user token against the Discord REST API violates Discord's Terms of
Service. This module is intended for personal, self-hosted automation only.
"""

from redeem_bot.discord.fetcher import fetch_all_channels, fetch_channel, load_cached_messages
from redeem_bot.discord.models import DiscordAuthor, DiscordMessage, FetchResult

__all__ = [
    "DiscordAuthor",
    "DiscordMessage",
    "FetchResult",
    "fetch_all_channels",
    "fetch_channel",
    "load_cached_messages",
]
