"""Code redemption HTTP client and response parsing."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from redeem_bot.redeem.auth import create_default_headers
from redeem_bot.redeem.heroes import HeroManager
from redeem_bot.redeem.html_utils import extract_select_options, get_token_from_html
from redeem_bot.redeem.models import RedemptionResult

logger = logging.getLogger(__name__)


class CodeRedeemer:
    """Redeems promo codes for a single authenticated account."""

    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        username: str,
        profile_html: str | None = None,
        hero_manager: HeroManager | None = None,
    ) -> None:
        self.client = client
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self.username = username
        self.profile_html = profile_html
        self.hero_manager = hero_manager or HeroManager()

    def _ensure_profile_html(self) -> str | None:
        if self.profile_html is None:
            try:
                response = self.client.get(f"{self.base_url}profile#redeem-panel")
                if response.status_code == 200:
                    self.profile_html = response.text
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch redeem panel: %s", exc)
        return self.profile_html

    def extract_token(self) -> str | None:
        html = self._ensure_profile_html()
        if not html:
            return None
        return get_token_from_html(html)

    def extract_hero_ids(self) -> dict[str, str]:
        html = self._ensure_profile_html()
        if not html:
            return {}

        heroes_by_id = extract_select_options(html, "hero")
        if not heroes_by_id:
            logger.warning("Could not find hero select dropdown")

        self.hero_manager.add_heroes_from_dict(heroes_by_id)
        return {name: hero_id for hero_id, name in heroes_by_id.items()}

    def prepare_redemption_request(
        self, code: str, hero_id: str, token: str
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        redeem_url = f"{self.base_url}profile/redeem"
        payload = {"_token": token, "hero": hero_id, "code": code}
        headers = create_default_headers(self.base_url)
        return redeem_url, payload, headers

    def parse_redemption_response(
        self,
        response: httpx.Response,
        hero_name: str,
        hero_id: str,
        code: str,
    ) -> RedemptionResult:
        try:
            result = response.json()
        except json.JSONDecodeError:
            return RedemptionResult.error_result(
                error_type="json_error",
                message="Invalid JSON response",
                account_username=self.username,
                hero_name=hero_name,
                hero_id=hero_id,
                response_status=response.status_code,
                raw_response=response.text[:500],
            )

        if isinstance(result, list) and len(result) >= 2 and result[0] == "success":
            items = result[1] if len(result) > 1 else {}
            return RedemptionResult.success_result(
                items=items,
                account_username=self.username,
                hero_name=hero_name,
                hero_id=hero_id,
                response_status=response.status_code,
                raw_response=str(result),
            )

        if isinstance(result, list) and len(result) >= 2 and result[0] == "error":
            error_data = result[1]

            if isinstance(error_data, str) and "can't use this code again" in error_data:
                return RedemptionResult.already_redeemed_result(
                    account_username=self.username,
                    hero_name=hero_name,
                    hero_id=hero_id,
                    response_status=response.status_code,
                    raw_response=str(result),
                )

            if isinstance(error_data, dict):
                return RedemptionResult.wrong_hero_class_result(
                    potential_items=error_data,
                    account_username=self.username,
                    hero_name=hero_name,
                    hero_id=hero_id,
                    response_status=response.status_code,
                    raw_response=str(result),
                )

            return RedemptionResult.error_result(
                error_type="other_info",
                message=str(error_data),
                account_username=self.username,
                hero_name=hero_name,
                hero_id=hero_id,
                response_status=response.status_code,
                raw_response=str(result),
            )

        return RedemptionResult.error_result(
            error_type="unexpected_format",
            message="Unexpected response format",
            account_username=self.username,
            hero_name=hero_name,
            hero_id=hero_id,
            response_status=response.status_code,
            raw_response=str(result),
        )

    def redeem_code(
        self,
        code: str,
        hero_id: str | None = None,
        hero_name: str | None = None,
    ) -> RedemptionResult:
        token = self.extract_token()
        if not token:
            return RedemptionResult.error_result(
                error_type="token_error",
                message="No CSRF token found",
                account_username=self.username,
                hero_name=hero_name or "",
                hero_id=hero_id or "",
            )

        heroes_dict: dict[str, str] | None = None
        if not hero_id:
            heroes_dict = self.extract_hero_ids()
            if not heroes_dict:
                return RedemptionResult.error_result(
                    error_type="hero_error",
                    message="No heroes found",
                    account_username=self.username,
                )
            hero_name = next(iter(heroes_dict))
            hero_id = heroes_dict[hero_name]

        hero_id = str(hero_id)

        if not hero_name:
            if heroes_dict is None:
                heroes_dict = self.extract_hero_ids()
            hero_name = next(
                (name for name, hid in heroes_dict.items() if str(hid) == hero_id),
                f"unknown_hero_{hero_id}",
            )

        try:
            redeem_url, payload, headers = self.prepare_redemption_request(
                code, hero_id, token
            )
            response = self.client.post(redeem_url, data=payload, headers=headers)
            return self.parse_redemption_response(response, hero_name, hero_id, code)
        except httpx.HTTPError as exc:
            return RedemptionResult.error_result(
                error_type="exception",
                message=str(exc),
                account_username=self.username,
                hero_name=hero_name,
                hero_id=hero_id,
                raw_response=type(exc).__name__,
            )

    def try_heroes_in_order(
        self,
        code: str,
        hero_names: list[str],
    ) -> RedemptionResult | None:
        """Try heroes in order; return first success or already-redeemed result."""
        for hero_name in hero_names:
            hero = self.hero_manager.heroes.get(hero_name)
            if hero is None:
                continue

            result = self.redeem_code(code, hero.id, hero_name)

            if result.success or result.is_already_redeemed:
                return result

            if result.is_wrong_hero_class:
                continue

        return None
