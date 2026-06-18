"""Redemption domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RedeemAllResult:
    """Outcomes from trying a code on every hero for every account."""

    code: str
    results: list[RedemptionResult] = field(default_factory=list)

    @property
    def successes(self) -> list[RedemptionResult]:
        return [result for result in self.results if result.success]

    @property
    def already_redeemed_results(self) -> list[RedemptionResult]:
        return [result for result in self.results if result.is_already_redeemed]

    def classify_outcome(self) -> tuple[str, str | None]:
        if self.successes:
            return "redeemed", None
        if self.already_redeemed_results:
            return "already_redeemed", "already_redeemed"
        return "probe_failed", "probe_failed"

    def to_probe_result(self) -> ProbeResult | None:
        """Best probe summary for logging/notifications."""
        if not self.results:
            return None
        for result in self.results:
            if result.success:
                return ProbeResult(
                    code=self.code,
                    hero_name=result.hero_name,
                    hero_id=result.hero_id,
                    items=result.items,
                    account_username=result.account_username,
                )
        for result in self.results:
            if result.is_already_redeemed:
                return ProbeResult(
                    code=self.code,
                    hero_name=result.hero_name,
                    hero_id=result.hero_id,
                    items={},
                    account_username=result.account_username,
                    already_redeemed=True,
                )
        first = self.results[0]
        return ProbeResult(
            code=self.code,
            hero_name=first.hero_name,
            hero_id=first.hero_id,
            items={},
            account_username=first.account_username,
        )


@dataclass
class ProbeResult:
    """Outcome of probing a code on the first account."""

    code: str
    hero_name: str
    hero_id: str
    items: dict[str, Any]
    account_username: str
    already_redeemed: bool = False


@dataclass
class RedemptionResult:
    """Result of a single redemption HTTP attempt."""

    success: bool
    message: str
    account_username: str = ""
    hero_name: str = ""
    hero_id: str = ""
    items: dict[str, Any] = field(default_factory=dict)
    potential_items: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    raw_response: str | None = None
    response_status: int = 0

    @property
    def is_already_redeemed(self) -> bool:
        return self.error_type == "already_redeemed"

    @property
    def is_wrong_hero_class(self) -> bool:
        return self.error_type == "wrong_hero_class"

    @classmethod
    def success_result(
        cls,
        items: dict[str, Any],
        account_username: str = "",
        hero_name: str = "",
        hero_id: str = "",
        message: str = "Redemption successful",
        response_status: int = 200,
        raw_response: str | None = None,
    ) -> RedemptionResult:
        return cls(
            success=True,
            message=message,
            account_username=account_username,
            hero_name=hero_name,
            hero_id=hero_id,
            items=items,
            error_type=None,
            raw_response=raw_response,
            response_status=response_status,
        )

    @classmethod
    def already_redeemed_result(
        cls,
        account_username: str = "",
        hero_name: str = "",
        hero_id: str = "",
        message: str = "Code already redeemed",
        response_status: int = 200,
        raw_response: str | None = None,
    ) -> RedemptionResult:
        return cls(
            success=False,
            message=message,
            account_username=account_username,
            hero_name=hero_name,
            hero_id=hero_id,
            error_type="already_redeemed",
            raw_response=raw_response,
            response_status=response_status,
        )

    @classmethod
    def wrong_hero_class_result(
        cls,
        potential_items: dict[str, Any],
        account_username: str = "",
        hero_name: str = "",
        hero_id: str = "",
        message: str = "Wrong hero class or faction for this code",
        response_status: int = 200,
        raw_response: str | None = None,
    ) -> RedemptionResult:
        return cls(
            success=False,
            message=message,
            account_username=account_username,
            hero_name=hero_name,
            hero_id=hero_id,
            potential_items=potential_items,
            error_type="wrong_hero_class",
            raw_response=raw_response,
            response_status=response_status,
        )

    @classmethod
    def error_result(
        cls,
        error_type: str,
        message: str,
        account_username: str = "",
        hero_name: str = "",
        hero_id: str = "",
        response_status: int = 0,
        raw_response: str | None = None,
    ) -> RedemptionResult:
        return cls(
            success=False,
            message=message,
            account_username=account_username,
            hero_name=hero_name,
            hero_id=hero_id,
            error_type=error_type,
            raw_response=raw_response,
            response_status=response_status,
        )
