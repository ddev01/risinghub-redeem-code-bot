"""Tests for tried-code tracking in SQLite."""

from __future__ import annotations

from pathlib import Path

from redeem_bot.storage.codes import (
    OUTCOME_PROBE_FAILED,
    OUTCOME_REDEEMED,
    OUTCOME_SKIPPED_BACKLOG,
    TriedCodeInput,
    filter_untried,
    get_tried_code,
    is_tried,
    mark_tried,
    mark_tried_batch,
)
from redeem_bot.extract.models import ExtractedCode
from redeem_bot.storage.db import init_db


def _extracted(name: str) -> ExtractedCode:
    return ExtractedCode(
        raw_text=name,
        normalized_code=name.upper(),
        source_message_id="1",
        source_channel="111",
    )


def _tried(name: str) -> TriedCodeInput:
    return TriedCodeInput(
        normalized_code=name.upper(),
        source_message_id="1",
        source_channel_id="111",
    )


def test_mark_tried_and_filter_untried(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    init_db(db_path)

    codes = [
        _extracted("CHRISTMAS-2025-RH-ROY"),
        _extracted("CHRISTMAS-2025-RH-ROY"),
        _extracted("RH-SUMMER-2026-NAT"),
    ]
    untried = filter_untried(db_path, codes)
    assert len(untried) == 2
    assert untried[0].normalized_code == "CHRISTMAS-2025-RH-ROY"
    assert untried[1].normalized_code == "RH-SUMMER-2026-NAT"

    mark_tried(db_path, _tried("CHRISTMAS-2025-RH-ROY"), OUTCOME_REDEEMED, dry_run=False)
    assert is_tried(db_path, "CHRISTMAS-2025-RH-ROY")

    remaining = filter_untried(db_path, codes)
    assert [item.normalized_code for item in remaining] == ["RH-SUMMER-2026-NAT"]

    stored = get_tried_code(db_path, "CHRISTMAS-2025-RH-ROY")
    assert stored is not None
    assert stored.outcome == OUTCOME_REDEEMED


def test_dry_run_does_not_mark_tried(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    init_db(db_path)

    mark_tried(db_path, _tried("TEST-CODE-ONE"), OUTCOME_PROBE_FAILED, dry_run=True)
    assert not is_tried(db_path, "TEST-CODE-ONE")


def test_mark_tried_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    init_db(db_path)

    codes = [_tried("ALPHA-1"), _tried("BETA-2")]
    marked = mark_tried_batch(db_path, codes, OUTCOME_SKIPPED_BACKLOG)
    assert marked == 2
    assert is_tried(db_path, "ALPHA-1")
    assert is_tried(db_path, "BETA-2")
    assert get_tried_code(db_path, "ALPHA-1").outcome == OUTCOME_SKIPPED_BACKLOG
