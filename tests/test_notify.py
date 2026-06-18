"""Unit tests for Discord webhook notifications."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
import typer

from redeem_bot.config import Settings
from redeem_bot.notify import (
    fatal_error_handler,
    notify_code_pipeline_debug,
    notify_fatal_error,
    notify_redemption_success,
)
from redeem_bot.notify.webhook import (
    DEBUG_EMBED_COLOR,
    FATAL_EMBED_COLOR,
    SUCCESS_EMBED_COLOR,
    build_code_debug_payload,
    build_discord_message_url,
    build_fatal_payload,
    build_success_payload,
    post_webhook,
)
from redeem_bot.extract.models import ExtractedCode
from redeem_bot.redeem.models import ProbeResult, RedemptionResult

FIXED_TIMESTAMP = "2026-06-18 12:00:00 UTC"
WEBHOOK_URL = "https://discord.com/api/webhooks/1234567890/test-token"


@pytest.fixture
def settings_with_webhook() -> Settings:
    return Settings(
        DISCORD_WEBHOOK_URL=WEBHOOK_URL,
        DISCORD_WEBHOOK_DEBUG=False,
        RISINGHUB_BASE_URL="https://example.test/",
    )


@pytest.fixture
def settings_without_webhook() -> Settings:
    return Settings(
        DISCORD_WEBHOOK_URL=None,
        DISCORD_WEBHOOK_DEBUG=False,
        RISINGHUB_BASE_URL="https://example.test/",
    )


class TestPayloadBuilders:
    def test_fatal_payload_includes_everyone_ping(self) -> None:
        payload = build_fatal_payload("run", RuntimeError("boom"), timestamp=FIXED_TIMESTAMP)

        assert payload["content"] == "@everyone"
        assert payload["allowed_mentions"] == {"parse": ["everyone"]}
        embed = payload["embeds"][0]
        assert embed["title"] == "Redeem bot failed"
        assert embed["color"] == FATAL_EMBED_COLOR
        fields = {field["name"]: field["value"] for field in embed["fields"]}
        assert fields["Command"] == "run"
        assert fields["Error"] == "boom"
        assert fields["Time (UTC)"] == FIXED_TIMESTAMP

    def test_success_payload_has_no_ping(self) -> None:
        payload = build_success_payload(
            code="SUMMER-SUN-RISINGHUB-2025",
            account="test_user_01",
            hero="test_hero_nat_gunner",
            items=["Gold", "XP"],
            source="channel=111 / msg=222",
            timestamp=FIXED_TIMESTAMP,
        )

        assert "content" not in payload
        assert "allowed_mentions" not in payload
        embed = payload["embeds"][0]
        assert embed["title"] == "Code redeemed"
        assert embed["color"] == SUCCESS_EMBED_COLOR
        fields = {field["name"]: field["value"] for field in embed["fields"]}
        assert fields["Code"] == "SUMMER-SUN-RISINGHUB-2025"
        assert fields["Account"] == "test_user_01"
        assert fields["Hero"] == "test_hero_nat_gunner"
        assert fields["Items"] == "Gold, XP"
        assert fields["Source"] == "channel=111 / msg=222"
        assert fields["Time (UTC)"] == FIXED_TIMESTAMP

    def test_debug_payload_includes_source_and_results(self) -> None:
        payload = build_code_debug_payload(
            code="GOLDEN-UBER-BACKSCRATCHER-NAT",
            author="test_user_01",
            channel_id="111",
            message_id="222",
            message_snippet="**Golden-Uber-Backscratcher-Nat**",
            message_url="https://discord.com/channels/999/111/222",
            probe_summary="OK — hero_a on test_user_01",
            redemption_summary="success: test_user_02 / hero_a — redeemed",
            skipped_reason=None,
            dry_run=False,
            timestamp=FIXED_TIMESTAMP,
        )

        embed = payload["embeds"][0]
        assert embed["title"] == "Code pipeline (debug)"
        assert embed["color"] == DEBUG_EMBED_COLOR
        fields = {field["name"]: field["value"] for field in embed["fields"]}
        assert fields["Author"] == "test_user_01"
        assert "discord.com/channels" in fields["Message"]
        assert fields["Message text"] == "**Golden-Uber-Backscratcher-Nat**"
        assert "hero_a" in fields["Probe"]
        assert "test_user_02" in fields["Redemptions"]

    def test_discord_message_url_requires_all_ids(self) -> None:
        assert (
            build_discord_message_url(guild_id="1", channel_id="2", message_id="3")
            == "https://discord.com/channels/1/2/3"
        )
        assert build_discord_message_url(guild_id=None, channel_id="2", message_id="3") is None


class TestDebugWebhook:
    @patch("redeem_bot.notify.webhook.httpx.post")
    def test_posts_when_debug_enabled(
        self,
        mock_post: MagicMock,
    ) -> None:
        mock_post.return_value = MagicMock(status_code=204, raise_for_status=MagicMock())
        settings = Settings(
            DISCORD_WEBHOOK_URL=WEBHOOK_URL,
            DISCORD_WEBHOOK_DEBUG=True,
            DISCORD_GUILD_ID="999",
            RISINGHUB_BASE_URL="https://example.test/",
        )
        extracted = ExtractedCode(
            raw_text="RH-SUMMER-2026-NAT",
            normalized_code="RH-SUMMER-2026-NAT",
            source_message_id="222",
            source_channel="111",
            source_author="test_user_01",
            source_snippet="Seasonal code RH-SUMMER-2026-NAT",
        )
        probe = ProbeResult(
            code="RH-SUMMER-2026-NAT",
            hero_name="hero_a",
            hero_id="1",
            items={"Gold": 100},
            account_username="test_user_01",
        )

        notify_code_pipeline_debug(
            extracted,
            probe=probe,
            redemptions=[
                RedemptionResult.success_result(
                    items={"Gold": 100},
                    account_username="test_user_02",
                    hero_name="hero_a",
                    hero_id="1",
                )
            ],
            skipped_reason=None,
            dry_run=False,
            settings=settings,
        )

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["embeds"][0]["title"] == "Code pipeline (debug)"

    @patch("redeem_bot.notify.webhook.httpx.post")
    def test_skips_when_debug_disabled(
        self,
        mock_post: MagicMock,
        settings_with_webhook: Settings,
    ) -> None:
        extracted = ExtractedCode(
            raw_text="RH-SUMMER-2026-NAT",
            normalized_code="RH-SUMMER-2026-NAT",
        )
        notify_code_pipeline_debug(
            extracted,
            probe=None,
            redemptions=[],
            skipped_reason="probe_failed",
            dry_run=False,
            settings=settings_with_webhook,
        )
        mock_post.assert_not_called()


class TestPostWebhook:
    @patch("redeem_bot.notify.webhook.httpx.post")
    def test_posts_fatal_payload(
        self,
        mock_post: MagicMock,
        settings_with_webhook: Settings,
    ) -> None:
        mock_post.return_value = MagicMock(status_code=204, raise_for_status=MagicMock())

        notify_fatal_error("fetch", ValueError("auth failed"), settings=settings_with_webhook)

        mock_post.assert_called_once()
        url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        assert url == WEBHOOK_URL
        assert kwargs["json"]["content"] == "@everyone"
        assert kwargs["timeout"] == 10.0

    @patch("redeem_bot.notify.webhook.httpx.post")
    def test_posts_success_payload_without_ping(
        self,
        mock_post: MagicMock,
        settings_with_webhook: Settings,
    ) -> None:
        mock_post.return_value = MagicMock(status_code=204, raise_for_status=MagicMock())

        notify_redemption_success(
            code="RH-SUMMER-2026-NAT",
            account="test_user_02",
            hero="test_hero_nat_mando",
            items="1000 Gold",
            source="channel=999 / msg=888",
            settings=settings_with_webhook,
        )

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert "content" not in payload
        assert payload["embeds"][0]["title"] == "Code redeemed"

    @patch("redeem_bot.notify.webhook.httpx.post")
    def test_skips_when_webhook_url_unset(
        self,
        mock_post: MagicMock,
        settings_without_webhook: Settings,
    ) -> None:
        post_webhook(build_fatal_payload("run", RuntimeError("x")), settings=settings_without_webhook)

        mock_post.assert_not_called()

    @patch("redeem_bot.notify.webhook.logger")
    @patch("redeem_bot.notify.webhook.httpx.post")
    def test_logs_http_failure_without_raising(
        self,
        mock_post: MagicMock,
        mock_logger: MagicMock,
        settings_with_webhook: Settings,
    ) -> None:
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=httpx.HTTPStatusError(
                "error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            ))
        )

        notify_fatal_error("run", RuntimeError("x"), settings=settings_with_webhook)

        mock_logger.warning.assert_called_once()


class TestFatalErrorHandler:
    @patch("redeem_bot.notify.notify_fatal_error")
    def test_decorator_notifies_and_reraises(self, mock_notify: MagicMock) -> None:
        @fatal_error_handler
        def failing_command() -> None:
            raise RuntimeError("pipeline crashed")

        with pytest.raises(RuntimeError, match="pipeline crashed"):
            failing_command()

        mock_notify.assert_called_once()
        command, error = mock_notify.call_args[0]
        assert command == "failing_command"
        assert str(error) == "pipeline crashed"

    @patch("redeem_bot.notify.notify_fatal_error")
    def test_decorator_passes_through_success(self, mock_notify: MagicMock) -> None:
        @fatal_error_handler
        def ok_command() -> str:
            return "done"

        assert ok_command() == "done"
        mock_notify.assert_not_called()

    @patch("redeem_bot.notify.notify_fatal_error")
    def test_decorator_does_not_treat_typer_exit_as_fatal(self, mock_notify: MagicMock) -> None:
        @fatal_error_handler
        def exit_command() -> None:
            raise typer.Exit(code=1)

        with pytest.raises(typer.Exit):
            exit_command()

        mock_notify.assert_not_called()
