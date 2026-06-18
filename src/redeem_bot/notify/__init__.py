"""Discord webhook notifications."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import typer

from redeem_bot.config import Settings

from .webhook import build_fatal_payload, build_success_payload, post_webhook
from .debug import notify_code_pipeline_debug

__all__ = [
    "fatal_error_handler",
    "notify_code_pipeline_debug",
    "notify_fatal_error",
    "notify_redemption_success",
]

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def notify_fatal_error(
    command: str,
    error: Exception,
    *,
    settings: Settings | None = None,
) -> None:
    """Send a fatal-error webhook with @everyone ping."""
    payload = build_fatal_payload(command, error)
    post_webhook(payload, settings=settings)


def notify_redemption_success(
    code: str,
    account: str,
    hero: str,
    items: str | list[str],
    source: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Send a success embed without pinging anyone."""
    payload = build_success_payload(code, account, hero, items, source)
    post_webhook(payload, settings=settings)


def fatal_error_handler(func: Callable[P, R]) -> Callable[P, R]:
    """Wrap a CLI command: notify on uncaught exceptions, then re-raise."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except typer.Exit:
            raise
        except Exception as exc:
            command = getattr(func, "__name__", "unknown")
            logger.exception("Unhandled error in %s", command)
            notify_fatal_error(command, exc)
            raise

    return wrapper
