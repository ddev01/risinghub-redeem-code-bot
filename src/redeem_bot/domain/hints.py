"""Faction/class hints embedded in promo codes."""

from __future__ import annotations

from dataclasses import dataclass

_FACTION_CLASS_TOKENS: dict[str, tuple[str, str]] = {
    "NATG": ("nat", "gunner"),
    "ROYG": ("roy", "gunner"),
    "NATM": ("nat", "mando"),
    "ROYM": ("roy", "mando"),
    "NATS": ("nat", "soldier"),
    "ROYS": ("roy", "soldier"),
}

_FACTION_TOKENS: dict[str, str] = {
    "NAT": "nat",
    "ROY": "roy",
}


@dataclass(frozen=True)
class CodeHints:
    """Optional faction/class hints extracted from a promo code."""

    faction: str | None = None
    hero_class: str | None = None

    def as_dict(self) -> dict[str, str]:
        hints: dict[str, str] = {}
        if self.faction is not None:
            hints["faction"] = self.faction
        if self.hero_class is not None:
            hints["class"] = self.hero_class
        return hints


def parse_hints(code: str) -> CodeHints:
    """Derive faction/class hints from uppercase code segments."""
    segments = code.upper().split("-")
    faction: str | None = None
    hero_class: str | None = None

    for segment in segments:
        if segment in _FACTION_CLASS_TOKENS:
            seg_faction, seg_class = _FACTION_CLASS_TOKENS[segment]
            faction = faction or seg_faction
            hero_class = hero_class or seg_class
            continue
        if segment in _FACTION_TOKENS:
            faction = faction or _FACTION_TOKENS[segment]

    return CodeHints(faction=faction, hero_class=hero_class)
