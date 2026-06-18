"""Tests for faction/class hints and hint-aware hero ordering."""

from __future__ import annotations

import random

from redeem_bot.domain.hints import CodeHints, parse_hints
from redeem_bot.redeem.heroes import HeroManager


def test_parse_hints_faction_class_tokens() -> None:
    hints = parse_hints("ASCE-NATG-1000")
    assert hints.faction == "nat"
    assert hints.hero_class == "gunner"
    assert hints.as_dict() == {"faction": "nat", "class": "gunner"}


def test_parse_hints_faction_only() -> None:
    hints = parse_hints("RH-SUMMER-2026-ROY")
    assert hints.faction == "roy"
    assert hints.hero_class is None


def test_hero_order_filters_by_faction_and_class() -> None:
    manager = HeroManager()
    manager.add_hero("test_hero_nat_gunner", "1")
    manager.add_hero("test_hero_roy_gunner", "2")
    manager.add_hero("test_hero_nat_soldier", "3")
    manager.set_priority_heroes(
        ["test_hero_roy_gunner", "test_hero_nat_gunner", "test_hero_nat_soldier"]
    )

    order = manager.get_redeem_hero_names(
        hints=CodeHints(faction="nat", hero_class="gunner"),
        rng=random.Random(0),
    )

    assert order == ["test_hero_nat_gunner"]


def test_hero_order_falls_back_when_hints_match_nothing() -> None:
    manager = HeroManager()
    manager.add_hero("test_hero_roy_mando", "1")
    manager.add_hero("test_hero_roy_gunner", "2")

    order = manager.get_redeem_hero_names(
        hints=CodeHints(faction="nat", hero_class="soldier"),
        rng=random.Random(0),
    )

    assert set(order) == {"test_hero_roy_mando", "test_hero_roy_gunner"}
