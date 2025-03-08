"""
Hero management functionality for the RisingHub code redemption bot.
"""

from typing import Dict, List, Optional, NamedTuple
from enum import Enum


class Faction(Enum):
    """
    The factions in the game.
    """

    NATIONAL = "nat"
    ROYALIST = "roy"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, faction_str: str) -> "Faction":
        """
        Convert a string to a Faction enum value.

        Args:
            faction_str: The faction string to convert

        Returns:
            The corresponding Faction enum value
        """
        faction_str = faction_str.lower()
        if faction_str == "nat" or faction_str == "national":
            return cls.NATIONAL
        elif faction_str == "roy" or faction_str == "royalist":
            return cls.ROYALIST
        else:
            return cls.UNKNOWN


class HeroClass(Enum):
    """
    The hero classes in the game.
    """

    MANDO = "mando"
    GUNNER = "gunner"
    SOLDIER = "soldier"
    UNKNOWN = "unknown"

    @classmethod
    def from_hero_name(cls, hero_name: str) -> "HeroClass":
        """
        Attempt to determine the hero class from the hero name.

        Args:
            hero_name: The hero name to analyze

        Returns:
            The most likely hero class based on the name
        """
        hero_name = hero_name.lower()
        if "mando" in hero_name:
            return cls.MANDO
        elif "gunner" in hero_name:
            return cls.GUNNER
        elif "soldier" in hero_name:
            return cls.SOLDIER
        else:
            return cls.UNKNOWN


class Hero(NamedTuple):
    """
    Represents a hero in the game.
    """

    name: str
    id: str
    faction: Faction = Faction.UNKNOWN
    hero_class: HeroClass = HeroClass.UNKNOWN

    @property
    def full_description(self) -> str:
        """
        Get a full description of the hero.

        Returns:
            A string describing the hero
        """
        return (
            f"{self.name} (ID: {self.id}, {self.faction.value} {self.hero_class.value})"
        )


class HeroManager:
    """
    Manages hero information and preferences.
    """

    def __init__(self):
        """
        Initialize the hero manager.
        """
        self.heroes: Dict[str, Hero] = {}
        self.priority_nat_hero: Optional[str] = None
        self.priority_roy_hero: Optional[str] = None
        self.priority_faction: Faction = Faction.UNKNOWN

    def add_hero(self, name: str, hero_id: str) -> Hero:
        """
        Add a hero to the manager.

        Args:
            name: The hero's name
            hero_id: The hero's ID

        Returns:
            The created Hero object
        """
        # Try to determine faction and class from the name
        faction = Faction.UNKNOWN
        if "nat" in name.lower():
            faction = Faction.NATIONAL
        elif "roy" in name.lower():
            faction = Faction.ROYALIST

        hero_class = HeroClass.from_hero_name(name)

        hero = Hero(name=name, id=hero_id, faction=faction, hero_class=hero_class)
        self.heroes[name] = hero
        return hero

    def add_heroes_from_dict(self, heroes_dict: Dict[str, str]) -> None:
        """
        Add multiple heroes from a dictionary.

        Args:
            heroes_dict: Dictionary mapping hero names to hero IDs
        """
        for name, hero_id in heroes_dict.items():
            self.add_hero(name, hero_id)

    def set_priority_heroes(
        self,
        priority_nat_hero: Optional[str] = None,
        priority_roy_hero: Optional[str] = None,
        priority_faction: str = "",
    ) -> None:
        """
        Set the priority heroes and faction.

        Args:
            priority_nat_hero: The name of the priority National hero
            priority_roy_hero: The name of the priority Royalist hero
            priority_faction: The priority faction (nat or roy)
        """
        self.priority_nat_hero = priority_nat_hero
        self.priority_roy_hero = priority_roy_hero
        self.priority_faction = Faction.from_string(priority_faction)

    def get_prioritized_hero_names(self) -> List[str]:
        """
        Get hero names in priority order.

        Returns:
            A list of hero names, sorted by priority
        """
        if not self.heroes:
            return []

        prioritized_heroes = []
        remaining_heroes = list(self.heroes.keys())

        # Check if we have valid priorities
        has_priorities = self.priority_faction != Faction.UNKNOWN and (
            self.priority_nat_hero or self.priority_roy_hero
        )

        if has_priorities:
            # First priority hero based on faction
            first_priority = (
                self.priority_nat_hero
                if self.priority_faction == Faction.NATIONAL
                else self.priority_roy_hero
            )
            second_priority = (
                self.priority_roy_hero
                if self.priority_faction == Faction.NATIONAL
                else self.priority_nat_hero
            )

            # Add first priority hero if it exists
            if first_priority and first_priority in remaining_heroes:
                prioritized_heroes.append(first_priority)
                remaining_heroes.remove(first_priority)

            # Add second priority hero if it exists
            if second_priority and second_priority in remaining_heroes:
                prioritized_heroes.append(second_priority)
                remaining_heroes.remove(second_priority)

        # Combine prioritized heroes with remaining ones
        return prioritized_heroes + remaining_heroes

    def to_dict(self) -> Dict[str, str]:
        """
        Convert heroes to a dictionary format for storage.

        Returns:
            A dictionary mapping hero names to hero IDs
        """
        return {hero.name: hero.id for hero in self.heroes.values()}
