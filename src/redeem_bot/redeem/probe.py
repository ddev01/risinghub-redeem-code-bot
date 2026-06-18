"""Probe-then-redeem-all orchestration."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import httpx

from redeem_bot.config import AccountSettings, Settings, get_settings
from redeem_bot.redeem.attempts import record_attempt, record_success
from redeem_bot.redeem.auth import get_authenticated_session, LoginManager
from redeem_bot.redeem.heroes import HeroManager
from redeem_bot.domain.hints import CodeHints
from redeem_bot.redeem.models import ProbeResult, RedeemAllResult, RedemptionResult
from redeem_bot.redeem.progress import RedeemBeforeCallback, RedeemResultCallback
from redeem_bot.redeem.redeemer import CodeRedeemer

logger = logging.getLogger(__name__)


def _cookie_path(settings: Settings, username: str) -> Path:
    return settings.sessions_dir / username / "cookies.json"


def _apply_account_priorities(hero_manager: HeroManager, account: AccountSettings) -> None:
    hero_manager.set_priority_heroes(account.priority_heroes)


def _record_result(
    db_path: Path,
    code: str,
    result: RedemptionResult,
) -> None:
    if result.success:
        record_success(
            db_path,
            code,
            result.account_username,
            result.hero_name,
            result.hero_id,
            result.items,
        )
        record_attempt(
            db_path,
            code,
            result.account_username,
            result.hero_name,
            result.hero_id,
            "success",
        )
    elif result.is_already_redeemed:
        record_attempt(
            db_path,
            code,
            result.account_username,
            result.hero_name,
            result.hero_id,
            "already_redeemed",
            result.message,
        )
    elif result.is_wrong_hero_class:
        record_attempt(
            db_path,
            code,
            result.account_username,
            result.hero_name,
            result.hero_id,
            "wrong_hero_class",
            result.message,
        )
    else:
        record_attempt(
            db_path,
            code,
            result.account_username,
            result.hero_name or None,
            result.hero_id or None,
            result.error_type or "error",
            result.message,
        )


def _open_redeemer(
    account: AccountSettings,
    settings: Settings,
    client: httpx.Client | None = None,
) -> tuple[CodeRedeemer | None, LoginManager | None]:
    cookie_file = _cookie_path(settings, account.username)
    session, profile_response = get_authenticated_session(
        settings.risinghub_base_url,
        account.username,
        account.password,
        cookie_file,
        client=client,
    )

    if session is None:
        logger.error("Authentication failed for %s", account.username)
        return None, None

    login_manager = LoginManager(
        settings.risinghub_base_url,
        cookie_file,
        client=session,
    )

    profile_html = profile_response.text if profile_response is not None else None
    hero_manager = HeroManager()
    _apply_account_priorities(hero_manager, account)

    redeemer = CodeRedeemer(
        client=session,
        base_url=settings.risinghub_base_url,
        username=account.username,
        profile_html=profile_html,
        hero_manager=hero_manager,
    )
    return redeemer, login_manager


def probe_code(
    accounts: list[AccountSettings],
    code: str,
    hints: CodeHints | None = None,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    client: httpx.Client | None = None,
    rng: random.Random | None = None,
    on_before: RedeemBeforeCallback | None = None,
    on_result: RedeemResultCallback | None = None,
) -> ProbeResult | None:
    """
    Probe a code on the first account, trying heroes in hint-aware priority order.

    Returns ProbeResult when a hero succeeds or the code was already redeemed on a hero.
    Returns None when all heroes fail or authentication fails.
    """
    if not accounts:
        return None

    if dry_run:
        account = accounts[0]
        hero_manager = HeroManager()
        for name in account.priority_heroes:
            hero_manager.add_hero(name, "dry-run")
        if not hero_manager.heroes:
            hero_manager.add_hero("dry-run-hero", "dry-run")
        _apply_account_priorities(hero_manager, account)
        order = hero_manager.get_redeem_hero_names(hints=hints, rng=rng)
        logger.info(
            "Dry-run probe for %s on %s — hero order: %s",
            code,
            account.username,
            order,
        )
        if order:
            return ProbeResult(
                code=code,
                hero_name=order[0],
                hero_id="dry-run",
                items={},
                account_username=account.username,
            )
        return None

    settings = settings or get_settings()
    db_path = settings.state_db_path
    account = accounts[0]

    redeemer, login_manager = _open_redeemer(account, settings, client=client)
    if redeemer is None:
        return None

    try:
        heroes = redeemer.extract_hero_ids()
        if not heroes:
            logger.error("No heroes found for probe account %s", account.username)
            return None

        hero_order = redeemer.hero_manager.get_redeem_hero_names(hints=hints, rng=rng)
        logger.info(
            "Probing %s on %s with %d heroes: %s",
            code,
            account.username,
            len(hero_order),
            hero_order,
        )

        last_already_redeemed: RedemptionResult | None = None

        for hero_name in hero_order:
            hero = redeemer.hero_manager.heroes.get(hero_name)
            if hero is None:
                continue

            if on_before is not None:
                on_before(code, account.username, hero_name)

            result = redeemer.redeem_code(code, hero.id, hero_name)
            _record_result(db_path, code, result)

            if on_result is not None:
                on_result(result)

            if result.success:
                return ProbeResult(
                    code=code,
                    hero_name=hero_name,
                    hero_id=hero.id,
                    items=result.items,
                    account_username=account.username,
                )

            if result.is_already_redeemed:
                last_already_redeemed = result
                continue

            if result.is_wrong_hero_class:
                continue

        if last_already_redeemed is not None:
            return ProbeResult(
                code=code,
                hero_name=last_already_redeemed.hero_name,
                hero_id=last_already_redeemed.hero_id,
                items={},
                account_username=account.username,
                already_redeemed=True,
            )

        return None
    finally:
        if login_manager is not None:
            login_manager.close()


def redeem_everywhere(
    accounts: list[AccountSettings],
    code: str,
    hints: CodeHints | None = None,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    client: httpx.Client | None = None,
    rng: random.Random | None = None,
    on_before: RedeemBeforeCallback | None = None,
    on_result: RedeemResultCallback | None = None,
) -> RedeemAllResult:
    """
    Try redeeming *code* on every hero for every account.

    Never stops early on already-redeemed — seasonal codes often need one redeem
    per hero, and we want to confirm each hero's status.
    """
    if not accounts:
        return RedeemAllResult(code=code)

    settings = settings or get_settings()
    db_path = settings.state_db_path

    if dry_run:
        account = accounts[0]
        hero_manager = HeroManager()
        for name in account.priority_heroes:
            hero_manager.add_hero(name, "dry-run")
        if not hero_manager.heroes:
            hero_manager.add_hero("dry-run-hero", "dry-run")
        _apply_account_priorities(hero_manager, account)
        hero_order = hero_manager.get_redeem_hero_names(hints=hints, rng=rng)
        dry_results: list[RedemptionResult] = []
        for account in accounts:
            for hero_name in hero_order:
                if on_before is not None:
                    on_before(code, account.username, hero_name)
                dry_result = RedemptionResult.success_result(
                    items={},
                    account_username=account.username,
                    hero_name=hero_name,
                    hero_id="dry-run",
                    message="Dry-run redemption",
                )
                dry_results.append(dry_result)
                if on_result is not None:
                    on_result(dry_result)
        return RedeemAllResult(code=code, results=dry_results)

    try:
        accounts_config = settings.load_accounts()
        delay = accounts_config.settings.rate_limit_delay
        account_delay = delay * accounts_config.settings.account_delay_multiplier
    except FileNotFoundError:
        delay = 2.0
        account_delay = 4.0

    results: list[RedemptionResult] = []

    for account_index, account in enumerate(accounts):
        redeemer, login_manager = _open_redeemer(account, settings, client=client)
        if redeemer is None:
            results.append(
                RedemptionResult.error_result(
                    error_type="auth_error",
                    message="Authentication failed",
                    account_username=account.username,
                )
            )
            continue

        try:
            heroes = redeemer.extract_hero_ids()
            if not heroes:
                logger.error("No heroes found for account %s", account.username)
                results.append(
                    RedemptionResult.error_result(
                        error_type="no_heroes",
                        message="No heroes found on profile",
                        account_username=account.username,
                    )
                )
                continue

            hero_order = redeemer.hero_manager.get_redeem_hero_names(hints=hints, rng=rng)
            logger.info(
                "Redeeming %s on %s — %d heroes: %s",
                code,
                account.username,
                len(hero_order),
                hero_order,
            )

            for hero_index, hero_name in enumerate(hero_order):
                hero = redeemer.hero_manager.heroes.get(hero_name)
                if hero is None:
                    continue

                if on_before is not None:
                    on_before(code, account.username, hero_name)

                result = redeemer.redeem_code(code, hero.id, hero_name)
                _record_result(db_path, code, result)
                results.append(result)

                if on_result is not None:
                    on_result(result)

                if hero_index < len(hero_order) - 1 and delay > 0:
                    time.sleep(delay)
        finally:
            if login_manager is not None:
                login_manager.close()

        if account_index < len(accounts) - 1 and account_delay > 0:
            time.sleep(account_delay)

    return RedeemAllResult(code=code, results=results)


def redeem_on_all_accounts(
    accounts: list[AccountSettings],
    code: str,
    hero_name: str,
    hero_id: str,
    skip_first: bool = False,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    client: httpx.Client | None = None,
) -> list[RedemptionResult]:
    """
    Redeem a code on multiple accounts using the same hero from a successful probe.

    When skip_first is True, accounts[0] is skipped (already probed).
  """
    if not accounts:
        return []

    settings = settings or get_settings()
    db_path = settings.state_db_path
    start_index = 1 if skip_first else 0
    targets = accounts[start_index:]

    if dry_run:
        return [
            RedemptionResult.success_result(
                items={},
                account_username=account.username,
                hero_name=hero_name,
                hero_id=hero_id,
                message="Dry-run redemption",
            )
            for account in targets
        ]

    results: list[RedemptionResult] = []
    try:
        accounts_config = settings.load_accounts()
        delay = accounts_config.settings.rate_limit_delay
        account_delay = delay * accounts_config.settings.account_delay_multiplier
    except FileNotFoundError:
        delay = 2.0
        account_delay = 4.0

    for index, account in enumerate(targets):
        redeemer, login_manager = _open_redeemer(account, settings, client=client)
        if redeemer is None:
            results.append(
                RedemptionResult.error_result(
                    error_type="auth_error",
                    message="Authentication failed",
                    account_username=account.username,
                    hero_name=hero_name,
                    hero_id=hero_id,
                )
            )
            continue

        try:
            result = redeemer.redeem_code(code, hero_id, hero_name)
            _record_result(db_path, code, result)
            results.append(result)
        finally:
            if login_manager is not None:
                login_manager.close()

        if index < len(targets) - 1 and account_delay > 0:
            time.sleep(account_delay)

    return results
