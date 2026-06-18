"""Deduplication helpers for extracted codes."""

from __future__ import annotations

from redeem_bot.extract.models import ExtractedCode


def dedupe_extracted_codes(codes: list[ExtractedCode]) -> list[ExtractedCode]:
    """Return codes with duplicates removed, preserving first occurrence order."""
    seen: set[str] = set()
    ordered: list[ExtractedCode] = []
    for code in codes:
        key = code.normalized_code.upper()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(code)
    return ordered
