"""Regex and heuristic promo code extraction."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from redeem_bot.domain.hints import parse_hints
from redeem_bot.extract.dedupe import dedupe_extracted_codes
from redeem_bot.extract.models import (
    ExtractedCode,
    ExtractReport,
    MessageExtraction,
)

_CODE_PATTERN = re.compile(r"\b([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)\b")

# Strip any http(s) URL before token matching (Tenor, Klipy, etc.)
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

_DATE_DMY_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_YEARLED_PROMO_PATTERN = re.compile(r"^2026-[A-Z0-9]+-", re.IGNORECASE)

_MIN_LENGTH = 8
_MAX_LENGTH = 80
_MIN_DASHES = 2
_MAX_SEGMENTS = 8
_MAX_SEGMENT_LENGTH = 16

# Exact normalized codes to always reject (jokes / spam)
_BLOCKLIST_EXACT = frozenset({"1-vp-code", "0-0-0-0-0"})

# Uppercase known promo families (fast accept + skip shape limits)
_KNOWN_PREFIXES = (
    "RH-",
    "MS15-",
    "ASCE-",
    "THNX-",
    "SUMMER-",
    "SPRING-",
    "CHRISTMAS-",
    "XXRH-",
    "2026-COTW-",
    "COTW-",
    "GOLDEN-UBER-",
    "WAITING-CODE-",
    "NEXT-DOTW-",
    "RHUB-",
    "RISING-",
    "FIREWORK-",
    "PK-FOR-",
    "HW2025-",
)


def _strip_trailing_punctuation(candidate: str) -> str:
    return candidate.rstrip(".,;:!?)\"']")


def _preprocess_text(text: str) -> str:
    """Remove http(s) URLs so path slugs are not matched as promo codes."""
    return _URL_PATTERN.sub(" ", text)


def _valid_segments(candidate: str) -> bool:
    return all(re.fullmatch(r"[A-Za-z0-9]+", segment) for segment in candidate.split("-"))


def _is_calendar_date(candidate: str) -> bool:
    if not _DATE_DMY_PATTERN.match(candidate):
        return False
    day, month, year = (int(part) for part in candidate.split("-"))
    return 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100


def _contains_url_scheme(candidate: str) -> bool:
    """Reject tokens that embed URL schemes or scheme-like segments."""
    lower = candidate.lower()
    if "http://" in lower or "https://" in lower:
        return True
    return any(segment in ("http", "https") for segment in lower.split("-"))


def _is_numeric_noise(candidate: str) -> bool:
    return all(segment.isdigit() for segment in candidate.split("-"))


def _has_known_promo_prefix(candidate: str) -> bool:
    upper = candidate.upper()
    if any(upper.startswith(prefix) for prefix in _KNOWN_PREFIXES):
        return True
    return bool(_YEARLED_PROMO_PATTERN.match(upper))


def _looks_like_promo_shape(candidate: str) -> bool:
    segments = candidate.split("-")
    if len(segments) > _MAX_SEGMENTS or len(candidate) > _MAX_LENGTH:
        return False
    return all(len(segment) <= _MAX_SEGMENT_LENGTH for segment in segments)


def _standalone_segments_ok(candidate: str) -> bool:
    segments = candidate.split("-")
    return 2 <= len(segments) <= _MAX_SEGMENTS and all(
        2 <= len(segment) <= _MAX_SEGMENT_LENGTH and segment.isalnum() for segment in segments
    )


def _is_blocklisted(candidate: str) -> bool:
    return candidate.lower() in _BLOCKLIST_EXACT


def is_valid_code(candidate: str, *, standalone: bool = False) -> bool:
    """Return True when *candidate* passes promo code heuristics."""
    normalized = _strip_trailing_punctuation(candidate.strip())
    if not normalized:
        return False
    if not (_MIN_LENGTH <= len(normalized) <= _MAX_LENGTH):
        return False
    if normalized.count("-") < _MIN_DASHES:
        return False
    if not _valid_segments(normalized):
        return False
    if _is_blocklisted(normalized):
        return False
    if _contains_url_scheme(normalized):
        return False
    if _is_calendar_date(normalized):
        return False
    if _is_numeric_noise(normalized):
        return False
    if _has_known_promo_prefix(normalized):
        return True
    if standalone and _standalone_segments_ok(normalized):
        return True
    return _looks_like_promo_shape(normalized)


def classify_candidate(candidate: str, *, standalone: bool = False) -> tuple[bool, str]:
    """Return (accepted, normalized_candidate)."""
    normalized = _strip_trailing_punctuation(candidate.strip())
    return is_valid_code(normalized, standalone=standalone), normalized


def _find_candidates(text: str) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for match in _CODE_PATTERN.finditer(_preprocess_text(text)):
        raw = match.group(1)
        normalized = _strip_trailing_punctuation(raw)
        key = normalized.upper()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(normalized)
    return candidates


def _is_standalone_in_content(content: str, normalized: str) -> bool:
    stripped = _strip_trailing_punctuation(content.strip())
    return stripped.upper() == normalized.upper()


def extract_from_text(text: str) -> list[ExtractedCode]:
    """Extract validated promo codes from plain message text."""
    preprocessed = _preprocess_text(text)
    extracted: list[ExtractedCode] = []
    for candidate in _find_candidates(text):
        standalone = _is_standalone_in_content(preprocessed, candidate)
        accepted, normalized = classify_candidate(candidate, standalone=standalone)
        if not accepted:
            continue
        normalized_code = normalized.upper()
        extracted.append(
            ExtractedCode(
                raw_text=candidate,
                normalized_code=normalized_code,
                hints=parse_hints(normalized_code),
            )
        )
    return extracted


def _parse_message_timestamp(message: dict) -> datetime | None:
    raw = message.get("timestamp") or message.get("created_at")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, str):
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _message_content(message: dict) -> str:
    content = message.get("content") or ""
    if content:
        return content
    embeds = message.get("embeds") or []
    parts: list[str] = []
    for embed in embeds:
        if not isinstance(embed, dict):
            continue
        for key in ("title", "description"):
            value = embed.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
    return "\n".join(parts)


def _message_author(message: dict) -> str:
    author = message.get("author")
    if isinstance(author, dict):
        username = author.get("username")
        if isinstance(username, str) and username:
            return username
    if isinstance(author, str):
        return author
    return "unknown"


def _snippet(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def extract_from_messages(messages: list[dict], since: datetime) -> ExtractReport:
    """Extract promo codes from Discord-style message dicts newer than *since*."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    extractions: list[MessageExtraction] = []
    processed = 0

    for message in messages:
        timestamp = _parse_message_timestamp(message)
        if timestamp is None or timestamp < since:
            continue

        processed += 1
        content = _message_content(message)
        preprocessed = _preprocess_text(content)
        candidates = _find_candidates(content)

        accepted_codes: list[ExtractedCode] = []
        rejected: list[str] = []

        message_id = str(message.get("id", ""))
        channel_id = str(message.get("channel_id", ""))
        author = _message_author(message)
        snippet = _snippet(content)

        for candidate in candidates:
            standalone = _is_standalone_in_content(preprocessed, candidate)
            ok, normalized = classify_candidate(candidate, standalone=standalone)
            if ok:
                normalized_code = normalized.upper()
                accepted_codes.append(
                    ExtractedCode(
                        raw_text=candidate,
                        normalized_code=normalized_code,
                        source_message_id=message_id or None,
                        source_channel=channel_id or None,
                        source_author=author,
                        source_snippet=snippet,
                        hints=parse_hints(normalized_code),
                    )
                )
            else:
                rejected.append(normalized)

        extractions.append(
            MessageExtraction(
                message_id=message_id,
                channel_id=channel_id,
                timestamp=timestamp,
                author=author,
                message_snippet=snippet,
                extracted_codes=accepted_codes,
                rejected_candidates=rejected,
            )
        )

    return ExtractReport(messages_processed=processed, extractions=extractions)


def unique_codes(report: ExtractReport) -> list[str]:
    """Sorted unique normalized codes from a report."""
    deduped = dedupe_extracted_codes(report.all_codes)
    return sorted(code.normalized_code for code in deduped)


def codes_with_authors(report: ExtractReport) -> list[tuple[str, str]]:
    """Each extracted code paired with the message author (sorted by code, then author)."""
    pairs: list[tuple[str, str]] = []
    for extraction in report.extractions:
        for code in extraction.extracted_codes:
            pairs.append((code.normalized_code, extraction.author))
    pairs.sort(key=lambda item: (item[0], item[1].lower()))
    return pairs
