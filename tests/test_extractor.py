"""Tests for promo code extraction heuristics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from redeem_bot.extract import (
    extract_from_messages,
    extract_from_text,
    is_valid_code,
)

FIXTURES = Path(__file__).parent / "fixtures"
DISCORD_MESSAGES = FIXTURES / "discord_messages.json"

POSITIVE_CODES = [
    "SUMMER-SUN-RISINGHUB-2025",
    "Jeep-Jump-And-Ram",
    "THNX-1000-ROY-SUBS",
    "THNX-1000-NAT-SUBS",
    "ASCE-NATG-1000",
    "ASCE-ROYM-1000",
    "MS15-ROYS-1000",
    "RH-SUMMER-2026-ROY",
    "RH-SUMMER-2026-NAT",
    "SPRING-2025-RH-NAT",
    "CHRISTMAS-2025-RH-ROY",
    "2026-HPPY-ESTR",
    "XXRH-BLCK-FRDY",
    "next-dotw-in-april",
    "waiting-code-royal",
    "waiting-code-national",
    "2026-COTW-FP2F-498W",
]

NEGATIVE_CODES = [
    "22-06-2026",
    "01-05-2026",
    "0-0-0-0-0",
    "1-VP-CODE",
    "ALL-ROADS-LEAD-TO-ROME-TIME-RABBIT-GIF-9497165517404307883",
]

HINT_EXPECTATIONS = {
    "THNX-1000-ROY-SUBS": {"faction": "roy"},
    "THNX-1000-NAT-SUBS": {"faction": "nat"},
    "ASCE-NATG-1000": {"faction": "nat", "class": "gunner"},
    "ASCE-ROYM-1000": {"faction": "roy", "class": "mando"},
    "MS15-ROYS-1000": {"faction": "roy", "class": "soldier"},
    "RH-SUMMER-2026-ROY": {"faction": "roy"},
    "RH-SUMMER-2026-NAT": {"faction": "nat"},
    "SPRING-2025-RH-NAT": {"faction": "nat"},
    "CHRISTMAS-2025-RH-ROY": {"faction": "roy"},
}


@pytest.mark.parametrize("code", POSITIVE_CODES)
def test_positive_codes_are_accepted(code: str) -> None:
    assert is_valid_code(code), f"expected accept: {code}"


@pytest.mark.parametrize("code", NEGATIVE_CODES)
def test_negative_codes_are_rejected(code: str) -> None:
    assert not is_valid_code(code), f"expected reject: {code}"


@pytest.mark.parametrize("code", POSITIVE_CODES)
def test_extract_from_text_finds_positive_code(code: str) -> None:
    extracted = extract_from_text(f"Use code {code} today!")
    normalized = {item.normalized_code for item in extracted}
    assert code.upper() in normalized


@pytest.mark.parametrize("code", NEGATIVE_CODES)
def test_extract_from_text_rejects_negative_code(code: str) -> None:
    extracted = extract_from_text(f"Placeholder {code} not ready")
    normalized = {item.normalized_code for item in extracted}
    assert code.upper() not in normalized


@pytest.mark.parametrize(
    "code,expected",
    [(code, HINT_EXPECTATIONS[code]) for code in HINT_EXPECTATIONS],
)
def test_hint_parsing(code: str, expected: dict[str, str]) -> None:
    extracted = extract_from_text(code)
    assert len(extracted) == 1
    assert extracted[0].hints_dict == expected


def test_deduplicates_repeated_codes_in_message() -> None:
    text = "RH-SUMMER-2026-NAT and again RH-SUMMER-2026-NAT"
    extracted = extract_from_text(text)
    assert len(extracted) == 1


def test_strips_trailing_punctuation() -> None:
    extracted = extract_from_text("Code: RH-SUMMER-2026-NAT.")
    assert len(extracted) == 1
    assert extracted[0].normalized_code == "RH-SUMMER-2026-NAT"


def test_accepts_long_segment_lottery_codes() -> None:
    for code in ("Golden-Uber-Backscratcher-Nat", "GOLDEN-UBER-BACKSCRATCHER-ROY"):
        assert is_valid_code(code)
        extracted = extract_from_text(code)
        assert extracted[0].normalized_code == code.upper()


def test_fixture_messages_cover_all_positive_codes() -> None:
    messages = json.loads(DISCORD_MESSAGES.read_text(encoding="utf-8"))
    since = datetime(2025, 3, 1, tzinfo=timezone.utc)
    report = extract_from_messages(messages, since=since)
    found = {code.normalized_code for code in report.all_codes}
    for code in POSITIVE_CODES:
        assert code.upper() in found, f"missing from fixture extraction: {code}"


def test_since_filter_skips_old_messages() -> None:
    messages = json.loads(DISCORD_MESSAGES.read_text(encoding="utf-8"))
    since = datetime(2025, 6, 1, tzinfo=timezone.utc)
    report = extract_from_messages(messages, since=since)
    message_ids = {extraction.message_id for extraction in report.extractions}
    assert "1000000000000000008" not in message_ids


def test_extract_report_includes_message_metadata() -> None:
    messages = json.loads(DISCORD_MESSAGES.read_text(encoding="utf-8"))
    since = datetime(2025, 6, 1, tzinfo=timezone.utc)
    report = extract_from_messages(messages, since=since)
    first = report.extractions[0]
    assert first.author == "test_user_01"
    assert first.channel_id == "900000000000000001"
    assert first.message_snippet


def test_rejects_expiry_dates_in_message() -> None:
    extracted = extract_from_text("New dotw! - expires 22-06-2026 21.30 CEST")
    assert not extracted


def test_strips_http_urls_before_extraction() -> None:
    url = "https://tenor.com/view/cat-cattitude-fun-cat-cat-fun-cat-funny-gif-5683118938279006051"
    extracted = extract_from_text(f"look {url}")
    assert not extracted


def test_rejects_token_containing_url_scheme() -> None:
    assert not is_valid_code("prefix-https-example-com-suffix")


def test_accepts_generic_lowercase_code() -> None:
    assert is_valid_code("some-promo-code")
    extracted = extract_from_text("redeem some-promo-code now")
    assert "SOME-PROMO-CODE" in {item.normalized_code for item in extracted}


def test_accepts_standalone_pasted_code() -> None:
    extracted = extract_from_text("FC2D-CBH1-1DZX")
    assert len(extracted) == 1
    assert extracted[0].normalized_code == "FC2D-CBH1-1DZX"


def test_extract_from_messages_propagates_source_metadata() -> None:
    messages = [
        {
            "id": "1000000000000000099",
            "channel_id": "900000000000000001",
            "timestamp": "2025-06-15T12:00:00+00:00",
            "author": {"username": "test_user_01"},
            "content": "RH-SUMMER-2026-NAT",
        }
    ]
    since = datetime(2025, 6, 1, tzinfo=timezone.utc)
    report = extract_from_messages(messages, since=since)
    code = report.all_codes[0]
    assert code.source_author == "test_user_01"
    assert code.source_snippet == "RH-SUMMER-2026-NAT"
    assert code.source_message_id == "1000000000000000099"


def test_unique_codes_sorted_deduped() -> None:
    from redeem_bot.extract.extractor import codes_with_authors, unique_codes

    messages = json.loads(DISCORD_MESSAGES.read_text(encoding="utf-8"))
    since = datetime(2025, 3, 1, tzinfo=timezone.utc)
    report = extract_from_messages(messages, since=since)
    codes = unique_codes(report)
    assert codes == sorted(set(codes))
    assert "RH-SUMMER-2026-NAT" in codes

    pairs = codes_with_authors(report)
    assert pairs
    assert all("\t" not in code and author for code, author in pairs)
    assert pairs == sorted(pairs, key=lambda item: (item[0], item[1].lower()))
