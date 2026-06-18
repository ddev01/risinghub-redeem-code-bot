"""Live redemption progress formatting and callbacks."""

from __future__ import annotations

from typing import Callable

from redeem_bot.redeem.models import RedemptionResult

RedeemBeforeCallback = Callable[[str, str, str], None]
RedeemResultCallback = Callable[[RedemptionResult], None]


def format_redemption_status(result: RedemptionResult) -> str:
    if result.success:
        status = "redeemed"
    elif result.is_already_redeemed:
        status = "already redeemed"
    elif result.is_wrong_hero_class:
        status = "wrong hero/class"
    else:
        status = result.error_type or "failed"
    hero = result.hero_name or "?"
    return f"{result.account_username} / {hero}: {status} — {result.message}"
