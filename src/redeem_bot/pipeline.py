"""Orchestration: fetch → extract → dedupe → redeem everywhere."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from redeem_bot.config import AccountSettings, Settings
from redeem_bot.discord.fetcher import fetch_all_channels
from redeem_bot.discord.models import FetchResult
from redeem_bot.domain.hints import parse_hints
from redeem_bot.extract.dedupe import dedupe_extracted_codes
from redeem_bot.extract.extractor import extract_from_messages
from redeem_bot.extract.models import ExtractedCode
from redeem_bot.messages import load_messages
from redeem_bot.notify import notify_code_pipeline_debug, notify_redemption_success
from redeem_bot.redeem import redeem_everywhere
from redeem_bot.redeem.models import ProbeResult, RedemptionResult
from redeem_bot.redeem.progress import RedeemBeforeCallback, RedeemResultCallback
from redeem_bot.storage.codes import (
    OUTCOME_PROBE_FAILED,
    OUTCOME_SKIPPED_BACKLOG,
    TriedCodeInput,
    filter_untried,
    get_tried_outcomes,
    is_tried,
    mark_tried,
    mark_tried_batch,
)
from redeem_bot.storage.db import init_db
from redeem_bot.storage.runs import finish_run_log, start_run_log
from redeem_bot.timeparse import parse_since
from redeem_bot.util.formatting import format_items

logger = logging.getLogger(__name__)


@dataclass
class CodeProcessResult:
    """Outcome of processing a single extracted code."""

    code: str
    probe: ProbeResult | None = None
    redemptions: list[RedemptionResult] = field(default_factory=list)
    skipped_reason: str | None = None


@dataclass
class PipelineResult:
    """Aggregate outcome of a pipeline run."""

    fetch_results: list[FetchResult] = field(default_factory=list)
    messages_processed: int = 0
    extracted_codes: int = 0
    new_codes: list[str] = field(default_factory=list)
    skipped_already_tried: int = 0
    skipped_tried_codes: list[str] = field(default_factory=list)
    processed: list[CodeProcessResult] = field(default_factory=list)
    dry_run: bool = False
    from_cache: bool = False

    @property
    def summary(self) -> str:
        processed_codes = sum(1 for item in self.processed if item.probe is not None)
        if self.dry_run:
            dry_run_actions = sum(
                1 + len(item.redemptions)
                for item in self.processed
                if item.probe is not None and item.skipped_reason is None
            )
            return (
                f"messages={self.messages_processed} extracted={self.extracted_codes} "
                f"new={len(self.new_codes)} skipped_tried={self.skipped_already_tried} "
                f"processed={processed_codes} dry_run_actions={dry_run_actions} "
                f"dry_run={self.dry_run}"
            )

        redeemed = sum(
            1
            for item in self.processed
            for result in item.redemptions
            if result.success
        )
        return (
            f"messages={self.messages_processed} extracted={self.extracted_codes} "
            f"new={len(self.new_codes)} skipped_tried={self.skipped_already_tried} "
            f"processed={processed_codes} redeemed={redeemed} "
            f"dry_run={self.dry_run}"
        )


def _tried_input(extracted: ExtractedCode) -> TriedCodeInput:
    return TriedCodeInput(
        normalized_code=extracted.normalized_code,
        source_message_id=extracted.source_message_id,
        source_channel_id=extracted.source_channel,
    )


def _source_label(extracted: ExtractedCode | None) -> str:
    if extracted is None:
        return "manual"
    channel = extracted.source_channel or "?"
    message = extracted.source_message_id or "?"
    return f"channel={channel} / msg={message}"


def list_pending_codes(
    settings: Settings,
    *,
    since: str | None = None,
) -> list[ExtractedCode]:
    """Codes that ``run`` would attempt (extracted from cache, not yet tried)."""
    settings.ensure_data_dirs()
    init_db(settings.state_db_path)
    since_dt = parse_since(since, settings)
    messages = load_messages(
        settings,
        since=since_dt,
        channel_id=None,
        from_cache=True,
    )
    report = extract_from_messages(messages, since=since_dt)
    unique_extracted = dedupe_extracted_codes(report.all_codes)
    return filter_untried(settings.state_db_path, unique_extracted)


def count_pending_codes(settings: Settings) -> int:
    """Count extracted codes in cache that have not been tried yet."""
    try:
        return len(list_pending_codes(settings))
    except Exception:
        return 0


def skip_pending_backlog(
    settings: Settings,
    *,
    since: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """
    Mark all pending cache codes as tried without redeeming.

    Use after manual testing or when an old Discord backlog would hammer RisingHub.
    """
    pending = list_pending_codes(settings, since=since)
    mark_tried_batch(
        settings.state_db_path,
        [_tried_input(code) for code in pending],
        OUTCOME_SKIPPED_BACKLOG,
        dry_run=dry_run,
    )
    return [code.normalized_code for code in pending]


def process_code(
    settings: Settings,
    accounts: list[AccountSettings],
    extracted: ExtractedCode,
    *,
    dry_run: bool = False,
    force: bool = False,
    on_before: RedeemBeforeCallback | None = None,
    on_result: RedeemResultCallback | None = None,
) -> CodeProcessResult:
    code = extracted.normalized_code
    hints = extracted.hints

    if not force and is_tried(settings.state_db_path, code):
        result = CodeProcessResult(code=code, skipped_reason="already_tried")
        notify_code_pipeline_debug(
            extracted,
            probe=None,
            redemptions=[],
            skipped_reason=result.skipped_reason,
            dry_run=dry_run,
            settings=settings,
        )
        return result

    redeem_all = redeem_everywhere(
        accounts,
        code,
        hints,
        settings=settings,
        dry_run=dry_run,
        on_before=on_before,
        on_result=on_result,
    )
    redemptions = redeem_all.results
    probe_result = redeem_all.to_probe_result()

    if not redemptions or probe_result is None:
        mark_tried(
            settings.state_db_path,
            _tried_input(extracted),
            OUTCOME_PROBE_FAILED,
            dry_run=dry_run,
        )
        result = CodeProcessResult(code=code, skipped_reason="probe_failed")
        notify_code_pipeline_debug(
            extracted,
            probe=None,
            redemptions=[],
            skipped_reason=result.skipped_reason,
            dry_run=dry_run,
            settings=settings,
        )
        return result

    source = _source_label(extracted)
    if not dry_run:
        for result in redeem_all.successes:
            notify_redemption_success(
                code=code,
                account=result.account_username,
                hero=result.hero_name,
                items=format_items(result.items),
                source=source,
                settings=settings,
            )

    outcome, skipped_reason = redeem_all.classify_outcome()

    mark_tried(
        settings.state_db_path,
        _tried_input(extracted),
        outcome,
        dry_run=dry_run,
    )
    notify_code_pipeline_debug(
        extracted,
        probe=probe_result,
        redemptions=redemptions,
        skipped_reason=skipped_reason,
        dry_run=dry_run,
        settings=settings,
    )
    return CodeProcessResult(
        code=code,
        probe=probe_result,
        redemptions=redemptions,
        skipped_reason=skipped_reason,
    )


def parse_code_list(value: str) -> list[str]:
    """Split comma-separated promo codes, normalize, dedupe, preserve order."""
    codes: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        normalized = part.strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        codes.append(normalized)
    return codes


def redeem_manual_code(
    settings: Settings,
    code: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    on_before: RedeemBeforeCallback | None = None,
    on_result: RedeemResultCallback | None = None,
) -> CodeProcessResult:
    """Redeem a single code entered via CLI."""
    settings.ensure_data_dirs()
    init_db(settings.state_db_path)
    accounts_config = settings.load_accounts()
    normalized = code.strip().upper()
    extracted = ExtractedCode(
        raw_text=code,
        normalized_code=normalized,
        hints=parse_hints(normalized),
    )
    return process_code(
        settings,
        accounts_config.accounts,
        extracted,
        dry_run=dry_run,
        force=force,
        on_before=on_before,
        on_result=on_result,
    )


def run_pipeline(
    settings: Settings,
    *,
    dry_run: bool = False,
    from_cache: bool = False,
    since: str | None = None,
    on_before: RedeemBeforeCallback | None = None,
    on_result: RedeemResultCallback | None = None,
) -> PipelineResult:
    """Execute fetch → extract → dedupe → redeem everywhere."""
    settings.ensure_data_dirs()
    init_db(settings.state_db_path)
    run_id = start_run_log(settings.state_db_path, "run")

    result = PipelineResult(dry_run=dry_run, from_cache=from_cache)
    try:
        since_dt = parse_since(since, settings)
        if not from_cache and since is None:
            result.fetch_results = fetch_all_channels(settings=settings)
            messages = load_messages(
                settings,
                since=since_dt,
                channel_id=None,
                from_cache=True,
            )
        else:
            messages = load_messages(
                settings,
                since=since_dt,
                channel_id=None,
                from_cache=from_cache,
                incremental_fetch=False,
            )
        report = extract_from_messages(messages, since=since_dt)
        result.messages_processed = report.messages_processed
        result.extracted_codes = len(report.all_codes)

        unique_extracted = dedupe_extracted_codes(report.all_codes)
        new_codes = filter_untried(settings.state_db_path, unique_extracted)
        new_code_set = {item.normalized_code for item in new_codes}
        skipped = [
            item.normalized_code
            for item in unique_extracted
            if item.normalized_code not in new_code_set
        ]
        result.skipped_already_tried = len(skipped)
        result.skipped_tried_codes = skipped
        result.new_codes = [item.normalized_code for item in new_codes]

        if skipped:
            outcomes = get_tried_outcomes(settings.state_db_path, skipped)
            for code in skipped:
                logger.info(
                    "Skipping %s: already tried (%s)",
                    code,
                    outcomes.get(code.upper(), "unknown"),
                )

        accounts_config = settings.load_accounts()
        accounts = accounts_config.accounts

        for extracted in new_codes:
            processed = process_code(
                settings,
                accounts,
                extracted,
                dry_run=dry_run,
                on_before=on_before,
                on_result=on_result,
            )
            result.processed.append(processed)
            logger.info(
                "Processed %s: hero=%s redemptions=%d reason=%s",
                extracted.normalized_code,
                processed.probe.hero_name if processed.probe else None,
                len(processed.redemptions),
                processed.skipped_reason,
            )

        finish_run_log(
            settings.state_db_path,
            run_id,
            status="ok",
            summary=result.summary,
        )
        return result
    except Exception:
        finish_run_log(
            settings.state_db_path,
            run_id,
            status="error",
            summary=result.summary,
        )
        raise
