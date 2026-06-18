"""Dry-run integration tests for the full pipeline."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from redeem_bot.config import Settings
from redeem_bot.pipeline import count_pending_codes, parse_code_list, run_pipeline, skip_pending_backlog
from redeem_bot.redeem.models import RedeemAllResult, RedemptionResult
from constants import CHANNEL_ID, POSITIVE_CODES
from helpers import seed_cache_from_messages
from redeem_bot.storage.codes import (
    OUTCOME_REDEEMED,
    OUTCOME_SKIPPED_BACKLOG,
    TriedCodeInput,
    get_tried_code,
    is_tried,
    mark_tried,
)
from redeem_bot.storage.db import connect, init_db

FIXTURES = Path(__file__).parent / "fixtures"
DISCORD_MESSAGES = FIXTURES / "discord_messages.json"


@pytest.fixture
def pipeline_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    accounts_file = tmp_path / "accounts.json"
    shutil.copy(
        Path(__file__).resolve().parents[1] / "config" / "accounts.example.json",
        accounts_file,
    )
    messages = json.loads(DISCORD_MESSAGES.read_text(encoding="utf-8"))
    seed_cache_from_messages(data_dir / "cache" / "messages", CHANNEL_ID, messages)

    return Settings(
        RISINGHUB_BASE_URL="https://example.test/",
        DISCORD_CHANNEL_IDS=CHANNEL_ID,
        DISCORD_FETCH_SINCE="2025-03-01T00:00:00Z",
        ACCOUNTS_FILE=accounts_file,
        DATA_DIR=data_dir,
        SQLITE_PATH=data_dir / "state.sqlite",
    )


def test_dry_run_pipeline_from_cache(pipeline_settings: Settings) -> None:
    result = run_pipeline(
        pipeline_settings,
        dry_run=True,
        from_cache=True,
        since="2025-03-01",
    )

    assert result.from_cache is True
    assert result.dry_run is True
    assert result.messages_processed >= 8
    assert result.extracted_codes >= len(POSITIVE_CODES)
    assert set(result.new_codes) == {code.upper() for code in POSITIVE_CODES}
    assert len(result.processed) == len(POSITIVE_CODES)
    assert all(item.probe is not None for item in result.processed)
    assert f"new={len(POSITIVE_CODES)}" in result.summary


def test_dry_run_does_not_mark_codes_tried(pipeline_settings: Settings) -> None:
    run_pipeline(pipeline_settings, dry_run=True, from_cache=True, since="2025-03-01")

    with connect(pipeline_settings.state_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM seen_codes").fetchone()["n"]

    assert count == 0


@patch("redeem_bot.pipeline.redeem_everywhere")
def test_live_run_marks_codes_tried(
    mock_redeem: MagicMock,
    pipeline_settings: Settings,
) -> None:
    mock_redeem.return_value = RedeemAllResult(
        code="RH-SUMMER-2026-NAT",
        results=[
            RedemptionResult.success_result(
                items={"Gold": 1},
                account_username="test_user_01",
                hero_name="test_hero_nat_gunner",
                hero_id="1",
            )
        ],
    )

    run_pipeline(pipeline_settings, dry_run=False, from_cache=True, since="2025-03-01")

    assert is_tried(pipeline_settings.state_db_path, "RH-SUMMER-2026-NAT")
    stored = get_tried_code(pipeline_settings.state_db_path, POSITIVE_CODES[0].upper())
    assert stored is not None
    assert stored.outcome == OUTCOME_REDEEMED


@patch("redeem_bot.pipeline.redeem_everywhere")
def test_second_run_skips_already_tried_codes(
    mock_redeem: MagicMock,
    pipeline_settings: Settings,
) -> None:
    mock_redeem.return_value = RedeemAllResult(
        code="RH-SUMMER-2026-NAT",
        results=[
            RedemptionResult.success_result(
                items={"Gold": 1},
                account_username="test_user_01",
                hero_name="test_hero_nat_gunner",
                hero_id="1",
            )
        ],
    )

    first = run_pipeline(pipeline_settings, dry_run=False, from_cache=True, since="2025-03-01")
    second = run_pipeline(pipeline_settings, dry_run=False, from_cache=True, since="2025-03-01")

    assert first.new_codes
    assert second.new_codes == []
    assert second.processed == []
    assert second.skipped_already_tried == len(first.new_codes)
    assert "CHRISTMAS-2025-RH-ROY" in second.skipped_tried_codes or second.skipped_already_tried > 0


def test_reposted_seasonal_code_counted_once_per_run(pipeline_settings: Settings) -> None:
    init_db(pipeline_settings.state_db_path)
    mark_tried(
        pipeline_settings.state_db_path,
        TriedCodeInput(normalized_code="CHRISTMAS-2025-RH-ROY"),
        OUTCOME_REDEEMED,
    )

    result = run_pipeline(pipeline_settings, dry_run=True, from_cache=True, since="2025-03-01")

    assert "CHRISTMAS-2025-RH-ROY" in result.skipped_tried_codes
    assert result.skipped_already_tried >= 1


def test_count_pending_codes(pipeline_settings: Settings) -> None:
    init_db(pipeline_settings.state_db_path)
    assert count_pending_codes(pipeline_settings) == len(POSITIVE_CODES)

    mark_tried(
        pipeline_settings.state_db_path,
        TriedCodeInput(normalized_code=POSITIVE_CODES[0].upper()),
        OUTCOME_REDEEMED,
    )
    assert count_pending_codes(pipeline_settings) == len(POSITIVE_CODES) - 1


def test_run_log_written(pipeline_settings: Settings) -> None:
    run_pipeline(pipeline_settings, dry_run=True, from_cache=True, since="2025-03-01")

    with connect(pipeline_settings.state_db_path) as conn:
        row = conn.execute(
            "SELECT command, status, summary FROM run_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert row is not None
    assert row["command"] == "run"
    assert row["status"] == "ok"
    assert f"new={len(POSITIVE_CODES)}" in row["summary"]


def test_parse_code_list() -> None:
    assert parse_code_list("ALPHA-1") == ["ALPHA-1"]
    assert parse_code_list("alpha-1,BETA-2") == ["ALPHA-1", "BETA-2"]
    assert parse_code_list(" A , B , A ") == ["A", "B"]
    assert parse_code_list("  ") == []


def test_skip_pending_backlog(pipeline_settings: Settings) -> None:
    init_db(pipeline_settings.state_db_path)
    assert count_pending_codes(pipeline_settings) == len(POSITIVE_CODES)

    skipped = skip_pending_backlog(pipeline_settings, since="2025-03-01")
    assert len(skipped) == len(POSITIVE_CODES)
    assert count_pending_codes(pipeline_settings) == 0

    stored = get_tried_code(pipeline_settings.state_db_path, POSITIVE_CODES[0].upper())
    assert stored is not None
    assert stored.outcome == OUTCOME_SKIPPED_BACKLOG

    result = run_pipeline(pipeline_settings, dry_run=False, from_cache=True, since="2025-03-01")
    assert result.new_codes == []
    assert result.processed == []
