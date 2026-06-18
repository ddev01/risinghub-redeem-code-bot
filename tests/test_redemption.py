"""Tests for redemption core: parsing, hero order, probe, and multi-account redeem."""

from __future__ import annotations

import json
import random
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from redeem_bot.config import AccountSettings, Settings
from redeem_bot.domain.hints import CodeHints
from redeem_bot.pipeline import redeem_manual_code
from redeem_bot.redeem.heroes import HeroManager
from redeem_bot.redeem.models import RedeemAllResult, RedemptionResult
from redeem_bot.redeem.probe import probe_code, redeem_everywhere, redeem_on_all_accounts
from redeem_bot.redeem.redeemer import CodeRedeemer

FIXTURES = Path(__file__).parent / "fixtures"
RESPONSES = json.loads((FIXTURES / "redemption_responses.json").read_text())

LOGIN_HTML = """
<html><head><meta name="_token" content="csrf-login-token"></head>
<body>Login</body></html>
"""

PROFILE_HTML = """
<html><head><meta name="_token" content="csrf-redeem-token"></head>
<body profile Dashboard>
<form>
<select name="hero">
  <option value="1">test_hero_nat_gunner</option>
  <option value="2">test_hero_nat_soldier</option>
  <option value="3">test_hero_roy_gunner</option>
  <option value="4">test_hero_roy_mando</option>
</select>
</form>
logout
</body></html>
"""


def _account(username: str, priority_heroes: list[str] | None = None) -> AccountSettings:
    return AccountSettings(
        username=username,
        password="test-password",
        priority_heroes=priority_heroes
        or [
            "test_hero_nat_gunner",
            "test_hero_roy_mando",
        ],
    )


def _mock_transport(redeem_sequence: list[object]) -> httpx.MockTransport:
    redeem_index = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal redeem_index
        path = request.url.path

        if path.endswith("/login"):
            if request.method == "POST":
                return httpx.Response(200, text=PROFILE_HTML)
            return httpx.Response(200, text=LOGIN_HTML)

        if path.endswith("/profile"):
            return httpx.Response(200, text=PROFILE_HTML)

        if path.endswith("/profile/redeem"):
            body = redeem_sequence[min(redeem_index, len(redeem_sequence) - 1)]
            redeem_index += 1
            if isinstance(body, dict) and "status" in body:
                return httpx.Response(200, json=body)
            return httpx.Response(200, json=body)

        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler)


def _test_settings(tmp_path: Path) -> Settings:
    return Settings(
        risinghub_base_url="https://example.test/",
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "data" / "state.sqlite",
    )


class TestResponseParsing:
    def test_success_response(self) -> None:
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
        redeemer = CodeRedeemer(client, "https://example.test/", "test_user_01")
        response = httpx.Response(200, json=RESPONSES["success"])
        result = redeemer.parse_redemption_response(
            response, "test_hero_nat_gunner", "1", "TEST-CODE"
        )
        assert result.success
        assert result.items["101"][2] == "Test Item"

    def test_already_redeemed_response(self) -> None:
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
        redeemer = CodeRedeemer(client, "https://example.test/", "test_user_01")
        response = httpx.Response(200, json=RESPONSES["already_redeemed"])
        result = redeemer.parse_redemption_response(
            response, "test_hero_nat_gunner", "1", "TEST-CODE"
        )
        assert result.is_already_redeemed
        assert not result.success

    def test_wrong_hero_class_response(self) -> None:
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
        redeemer = CodeRedeemer(client, "https://example.test/", "test_user_01")
        response = httpx.Response(200, json=RESPONSES["wrong_hero_nat"])
        result = redeemer.parse_redemption_response(
            response, "test_hero_roy_mando", "4", "TEST-CODE"
        )
        assert result.is_wrong_hero_class
        assert "201" in result.potential_items

    def test_other_error_response(self) -> None:
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
        redeemer = CodeRedeemer(client, "https://example.test/", "test_user_01")
        response = httpx.Response(200, json=RESPONSES["invalid_code"])
        result = redeemer.parse_redemption_response(
            response, "test_hero_nat_gunner", "1", "TEST-CODE"
        )
        assert not result.success
        assert result.error_type == "other_info"


class TestHeroOrdering:
    def test_priority_list_order(self) -> None:
        manager = HeroManager()
        manager.add_heroes_from_dict(
            {
                "1": "test_hero_nat_gunner",
                "2": "test_hero_nat_soldier",
                "3": "test_hero_roy_gunner",
                "4": "test_hero_roy_mando",
            }
        )
        manager.set_priority_heroes(
            [
                "test_hero_roy_mando",
                "test_hero_roy_gunner",
                "test_hero_nat_soldier",
            ]
        )
        order = manager.get_redeem_hero_names(rng=random.Random(0))
        assert order[:3] == [
            "test_hero_roy_mando",
            "test_hero_roy_gunner",
            "test_hero_nat_soldier",
        ]
        assert set(order[3:]) == {"test_hero_nat_gunner"}

    def test_unknown_priority_names_skipped(self) -> None:
        manager = HeroManager()
        manager.add_heroes_from_dict({"1": "test_hero_nat_gunner"})
        manager.set_priority_heroes(["missing_hero", "test_hero_nat_gunner"])
        order = manager.get_redeem_hero_names()
        assert order == ["test_hero_nat_gunner"]

    def test_no_priority_shuffles_all_heroes(self) -> None:
        manager = HeroManager()
        manager.add_heroes_from_dict(
            {
                "1": "test_hero_nat_gunner",
                "2": "test_hero_nat_soldier",
                "3": "test_hero_roy_gunner",
            }
        )
        orders = {
            tuple(manager.get_redeem_hero_names(rng=random.Random(seed)))
            for seed in range(20)
        }
        assert len(orders) > 1

    def test_priorities_on_same_manager_instance(self) -> None:
        """Regression: priority heroes must apply to the redeemer's hero manager."""
        manager = HeroManager()
        manager.add_heroes_from_dict(
            {
                "1": "test_hero_nat_gunner",
                "4": "test_hero_roy_mando",
            }
        )
        manager.set_priority_heroes(["test_hero_roy_mando", "test_hero_nat_gunner"])
        order = manager.get_redeem_hero_names()
        assert order[0] == "test_hero_roy_mando"


class TestProbeFlow:
    def test_probe_succeeds_on_third_hero(self, tmp_path: Path) -> None:
        settings = _test_settings(tmp_path)
        transport = _mock_transport(
            [
                RESPONSES["wrong_hero_nat"],
                RESPONSES["wrong_hero_nat"],
                RESPONSES["success"],
            ]
        )
        client = httpx.Client(transport=transport)
        account = _account(
            "test_user_01",
            priority_heroes=[
                "test_hero_nat_gunner",
                "test_hero_roy_mando",
                "test_hero_nat_soldier",
            ],
        )

        result = probe_code(
            [account],
            "TEST-CODE",
            settings=settings,
            client=client,
            rng=random.Random(0),
        )

        assert result is not None
        assert result.hero_name == "test_hero_nat_soldier"
        assert result.hero_id == "2"
        assert result.items["101"][2] == "Test Item"
        assert not result.already_redeemed

    def test_probe_fails_when_all_heroes_wrong(self, tmp_path: Path) -> None:
        settings = _test_settings(tmp_path)
        transport = _mock_transport(
            [
                RESPONSES["wrong_hero_nat"],
                RESPONSES["wrong_hero_nat"],
                RESPONSES["wrong_hero_nat"],
                RESPONSES["wrong_hero_nat"],
            ]
        )
        client = httpx.Client(transport=transport)

        result = probe_code(
            [_account("test_user_01")],
            "TEST-CODE",
            settings=settings,
            client=client,
        )

        assert result is None

    def test_probe_continues_after_already_redeemed(self, tmp_path: Path) -> None:
        settings = _test_settings(tmp_path)
        transport = _mock_transport(
            [RESPONSES["already_redeemed"], RESPONSES["success"]]
        )
        client = httpx.Client(transport=transport)

        result = probe_code(
            [_account("test_user_01")],
            "TEST-CODE",
            settings=settings,
            client=client,
        )

        assert result is not None
        assert not result.already_redeemed
        assert result.hero_name == "test_hero_roy_mando"

    def test_redeem_everywhere_tries_all_heroes(self, tmp_path: Path) -> None:
        settings = _test_settings(tmp_path)
        transport = _mock_transport(
            [
                RESPONSES["already_redeemed"],
                RESPONSES["already_redeemed"],
                RESPONSES["already_redeemed"],
                RESPONSES["already_redeemed"],
            ]
        )
        client = httpx.Client(transport=transport)

        result = redeem_everywhere(
            [_account("test_user_01")],
            "TEST-CODE",
            settings=settings,
            client=client,
        )

        assert len(result.results) == 4
        assert all(r.is_already_redeemed for r in result.results)

    def test_probe_dry_run(self) -> None:
        result = probe_code(
            [_account("test_user_01")],
            "TEST-CODE",
            hints=CodeHints(faction="nat"),
            dry_run=True,
        )
        assert result is not None
        assert result.hero_id == "dry-run"


class TestMultiAccountRedeem:
    def test_redeem_on_remaining_accounts(self, tmp_path: Path) -> None:
        settings = _test_settings(tmp_path)
        transport = _mock_transport([RESPONSES["success"], RESPONSES["success"]])
        client = httpx.Client(transport=transport)

        accounts = [
            _account("test_user_01"),
            _account("test_user_02"),
            _account("test_user_03"),
        ]

        results = redeem_on_all_accounts(
            accounts,
            "TEST-CODE",
            "test_hero_nat_gunner",
            "1",
            skip_first=True,
            settings=settings,
            client=client,
        )

        assert len(results) == 2
        assert all(r.success for r in results)
        assert results[0].account_username == "test_user_02"
        assert results[1].account_username == "test_user_03"

    def test_redeem_dry_run(self) -> None:
        accounts = [_account("test_user_01"), _account("test_user_02")]
        results = redeem_on_all_accounts(
            accounts,
            "TEST-CODE",
            "test_hero_nat_gunner",
            "1",
            skip_first=True,
            dry_run=True,
        )
        assert len(results) == 1
        assert results[0].success
        assert results[0].message == "Dry-run redemption"

    def test_redeem_everywhere_multi_account(self, tmp_path: Path) -> None:
        settings = _test_settings(tmp_path)
        transport = _mock_transport(
            [
                RESPONSES["wrong_hero_nat"],
                RESPONSES["success"],
                RESPONSES["success"],
                RESPONSES["success"],
                RESPONSES["success"],
                RESPONSES["success"],
                RESPONSES["success"],
                RESPONSES["success"],
            ]
        )
        client = httpx.Client(transport=transport)

        accounts = [_account("test_user_01"), _account("test_user_02")]

        result = redeem_everywhere(
            accounts,
            "TEST-CODE",
            settings=settings,
            client=client,
        )

        assert len(result.results) == 8
        successes = [r for r in result.results if r.success]
        assert len(successes) == 7
        assert successes[0].hero_name == "test_hero_roy_mando"
        assert sum(1 for r in successes if r.account_username == "test_user_01") == 3
        assert sum(1 for r in successes if r.account_username == "test_user_02") == 4


@patch("redeem_bot.pipeline.redeem_everywhere")
@patch("redeem_bot.pipeline.notify_redemption_success")
def test_redeem_manual_code_live_path(
    mock_notify: MagicMock,
    mock_redeem_all: MagicMock,
    tmp_path: Path,
) -> None:
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(
        '{"accounts": [{"username": "test_user_01", "password": "x", '
        '"priority_heroes": ["test_hero_nat_gunner", "test_hero_roy_gunner"]}], '
        '"settings": {}}',
        encoding="utf-8",
    )
    settings = Settings(
        RISINGHUB_BASE_URL="https://example.test/",
        DATA_DIR=tmp_path / "data",
        SQLITE_PATH=tmp_path / "data" / "state.sqlite",
        ACCOUNTS_FILE=accounts_file,
    )

    mock_redeem_all.return_value = RedeemAllResult(
        code="RH-SUMMER-2026-NAT",
        results=[
            RedemptionResult.success_result(
                items={"Gold": 100},
                account_username="test_user_01",
                hero_name="test_hero_nat_gunner",
                hero_id="hero-1",
            )
        ],
    )

    outcome = redeem_manual_code(settings, "RH-SUMMER-2026-NAT", dry_run=False)

    assert outcome.probe is not None
    mock_redeem_all.assert_called_once()
    mock_notify.assert_called_once()


class TestAccountConfig:
    def test_legacy_priority_fields_migrated(self) -> None:
        account = AccountSettings.model_validate(
            {
                "username": "test_user_01",
                "password": "secret",
                "priority_nat_hero": "test_hero_nat_gunner",
                "priority_roy_hero": "test_hero_roy_mando",
                "priority_faction": "roy",
            }
        )
        assert account.priority_heroes == [
            "test_hero_roy_mando",
            "test_hero_nat_gunner",
        ]


class TestRedeemProgress:
    def test_redeem_everywhere_invokes_progress_callbacks(self, tmp_path: Path) -> None:
        settings = _test_settings(tmp_path)
        transport = _mock_transport([RESPONSES["success"]])
        client = httpx.Client(transport=transport)
        attempts: list[str] = []
        results: list[str] = []

        redeem_everywhere(
            [_account("test_user_01", priority_heroes=["test_hero_nat_gunner"])],
            "TEST-CODE",
            settings=settings,
            client=client,
            rng=random.Random(0),
            on_before=lambda code, account, hero: attempts.append(f"{account}/{hero}"),
            on_result=lambda result: results.append(result.hero_name),
        )

        assert len(attempts) == 4
        assert attempts[0] == "test_user_01/test_hero_nat_gunner"
        assert len(results) == 4
        assert results[0] == "test_hero_nat_gunner"
