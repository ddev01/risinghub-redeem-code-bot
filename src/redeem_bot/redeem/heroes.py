"""Hero management and redemption ordering."""

from __future__ import annotations

import random
from enum import Enum
from typing import NamedTuple

from redeem_bot.domain.hints import CodeHints


class Faction(Enum):
    NATIONAL = "nat"
    ROYALIST = "roy"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, faction_str: str) -> Faction:
        faction_str = faction_str.lower()
        if faction_str in ("nat", "national"):
            return cls.NATIONAL
        if faction_str in ("roy", "royalist"):
            return cls.ROYALIST
        return cls.UNKNOWN


class HeroClass(Enum):
    MANDO = "mando"
    GUNNER = "gunner"
    SOLDIER = "soldier"
    UNKNOWN = "unknown"

    @classmethod
    def from_hero_name(cls, hero_name: str) -> HeroClass:
        hero_name = hero_name.lower()
        if "mando" in hero_name:
            return cls.MANDO
        if "gunner" in hero_name:
            return cls.GUNNER
        if "soldier" in hero_name:
            return cls.SOLDIER
        return cls.UNKNOWN

    @classmethod
    def from_hint(cls, value: str) -> HeroClass:
        value = value.lower()
        for member in cls:
            if member.value == value:
                return member
        return cls.UNKNOWN


class Hero(NamedTuple):
    name: str
    id: str
    faction: Faction = Faction.UNKNOWN
    hero_class: HeroClass = HeroClass.UNKNOWN


class HeroManager:
    """Manages hero metadata and redemption order."""

    def __init__(self) -> None:
        self.heroes: dict[str, Hero] = {}
        self.priority_heroes: list[str] = []

    def add_hero(self, name: str, hero_id: str) -> Hero:
        faction = Faction.UNKNOWN
        name_lower = name.lower()
        if "nat" in name_lower:
            faction = Faction.NATIONAL
        elif "roy" in name_lower:
            faction = Faction.ROYALIST

        hero = Hero(
            name=name,
            id=hero_id,
            faction=faction,
            hero_class=HeroClass.from_hero_name(name),
        )
        self.heroes[name] = hero
        return hero

    def add_heroes_from_dict(self, heroes_dict: dict[str, str]) -> None:
        for hero_id, name in heroes_dict.items():
            self.add_hero(name, hero_id)

    def set_priority_heroes(self, priority_heroes: list[str] | None = None) -> None:
        self.priority_heroes = list(priority_heroes or [])

    def get_redeem_hero_names(
        self,
        *,
        hints: CodeHints | None = None,
        rng: random.Random | None = None,
    ) -> list[str]:
        """
        Hero order for redemption.

        When ``hints`` specify faction/class, heroes are filtered to matches first
        (falls back to all profile heroes when none match). Configured
        ``priority_heroes`` come first within the candidate set; remaining heroes
        are shuffled randomly.
        """
        if not self.heroes:
            return []

        rng = rng or random.Random()
        available = set(self.heroes.keys())
        candidates = self._heroes_matching_hints(available, hints)

        if self.priority_heroes:
            ordered: list[str] = []
            seen: set[str] = set()
            for name in self.priority_heroes:
                if name in candidates and name not in seen:
                    ordered.append(name)
                    seen.add(name)
            remaining = [name for name in candidates if name not in seen]
            rng.shuffle(remaining)
            return ordered + remaining

        names = list(candidates)
        rng.shuffle(names)
        return names

    def _heroes_matching_hints(
        self,
        available: set[str],
        hints: CodeHints | None,
    ) -> set[str]:
        if hints is None or (hints.faction is None and hints.hero_class is None):
            return available

        hint_faction = Faction.from_string(hints.faction or "")
        hint_class = HeroClass.from_hint(hints.hero_class or "")

        matched: set[str] = set()
        for name in available:
            hero = self.heroes[name]
            faction_ok = hint_faction == Faction.UNKNOWN or hero.faction == hint_faction
            class_ok = hint_class == HeroClass.UNKNOWN or hero.hero_class == hint_class
            if faction_ok and class_ok:
                matched.add(name)

        return matched if matched else available

    def to_dict(self) -> dict[str, str]:
        return {hero.name: hero.id for hero in self.heroes.values()}
