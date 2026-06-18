"""Small shared formatting helpers."""

from __future__ import annotations

from typing import Any


def format_items(items: dict[str, Any]) -> str:
    if not items:
        return "—"
    return ", ".join(f"{key}: {value}" for key, value in items.items())
