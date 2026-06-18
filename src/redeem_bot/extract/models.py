"""Data models for code extraction results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from redeem_bot.domain.hints import CodeHints


@dataclass(frozen=True)
class ExtractedCode:
    """A validated promo code extracted from message text."""

    raw_text: str
    normalized_code: str
    source_message_id: str | None = None
    source_channel: str | None = None
    source_author: str | None = None
    source_snippet: str | None = None
    hints: CodeHints = field(default_factory=CodeHints)

    @property
    def hints_dict(self) -> dict[str, str]:
        return self.hints.as_dict()


@dataclass(frozen=True)
class MessageExtraction:
    """Extraction outcome for a single Discord message."""

    message_id: str
    channel_id: str
    timestamp: datetime
    author: str
    message_snippet: str
    extracted_codes: list[ExtractedCode]
    rejected_candidates: list[str]


@dataclass(frozen=True)
class ExtractReport:
    """Aggregate report across multiple messages."""

    messages_processed: int
    extractions: list[MessageExtraction]

    @property
    def all_codes(self) -> list[ExtractedCode]:
        codes: list[ExtractedCode] = []
        for extraction in self.extractions:
            codes.extend(extraction.extracted_codes)
        return codes
