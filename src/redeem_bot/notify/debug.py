"""Debug webhook helpers for pipeline accuracy monitoring."""

from __future__ import annotations

from redeem_bot.config import Settings
from redeem_bot.extract.models import ExtractedCode
from redeem_bot.redeem.models import ProbeResult, RedemptionResult
from redeem_bot.util.formatting import format_items

from .webhook import build_code_debug_payload, build_discord_message_url, post_webhook


def format_probe_summary(
    probe: ProbeResult | None,
    *,
    skipped_reason: str | None,
) -> str:
    if skipped_reason == "probe_failed":
        return "Failed — code invalid, expired, or not redeemable"
    if skipped_reason == "already_tried":
        return "Skipped — this code was already attempted in a previous run"
    if skipped_reason == "already_redeemed":
        account = probe.account_username if probe else "?"
        hero = probe.hero_name if probe else "?"
        return f"Already redeemed (account {account} / {hero})"
    if probe is None:
        return "—"
    return (
        f"OK — hero {probe.hero_name} ({probe.hero_id}) on {probe.account_username}; "
        f"items: {format_items(probe.items)}"
    )


def format_redemption_summary(redemptions: list[RedemptionResult]) -> str:
    if not redemptions:
        return "—"
    lines: list[str] = []
    for result in redemptions:
        status = "success" if result.success else "failed"
        detail = result.message
        if result.success and result.items:
            detail = f"{detail}; items: {format_items(result.items)}"
        lines.append(f"{status}: {result.account_username} / {result.hero_name} — {detail}")
    return "\n".join(lines)


def notify_code_pipeline_debug(
    extracted: ExtractedCode,
    *,
    probe: ProbeResult | None,
    redemptions: list[RedemptionResult],
    skipped_reason: str | None,
    dry_run: bool,
    settings: Settings | None = None,
) -> None:
    """Post a verbose webhook trace when DISCORD_WEBHOOK_DEBUG is enabled."""
    from redeem_bot.config import get_settings

    resolved = settings or get_settings()
    if not resolved.discord_webhook_debug:
        return

    message_url = build_discord_message_url(
        guild_id=resolved.discord_guild_id,
        channel_id=extracted.source_channel,
        message_id=extracted.source_message_id,
    )
    payload = build_code_debug_payload(
        code=extracted.normalized_code,
        author=extracted.source_author,
        channel_id=extracted.source_channel,
        message_id=extracted.source_message_id,
        message_snippet=extracted.source_snippet,
        message_url=message_url,
        probe_summary=format_probe_summary(probe, skipped_reason=skipped_reason),
        redemption_summary=format_redemption_summary(redemptions),
        skipped_reason=skipped_reason,
        dry_run=dry_run,
    )
    post_webhook(payload, settings=resolved)
