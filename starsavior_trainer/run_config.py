"""Run configuration shared by CLI, GUI, and pre-journey helpers."""

from __future__ import annotations

from dataclasses import dataclass


STAMINA_IMPRINT_PROFESSIONS = frozenset({"辅助", "坦克"})
POWER_IMPRINT_PROFESSIONS = frozenset({"术师", "刺客", "战士", "游侠"})


@dataclass(frozen=True)
class PreJourneyConfig:
    """Configuration for the main-menu-to-journey setup flow."""

    difficulty: str = "default"
    character_name: str = ""
    profession: str = ""
    imprint_slot_1_index: int = 1
    imprint_slot_2_index: int = 1
    support_deck: int = 1
    friend_support_name: str = ""

    def imprint_attribute(self) -> str:
        """Return the imprint attribute filter requested by the current profession."""
        if self.character_name == "艾黛":
            return "韧性"
        if self.profession in STAMINA_IMPRINT_PROFESSIONS:
            return "体力"
        return "力量"
