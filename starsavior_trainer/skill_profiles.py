"""Skill priority profiles migrated from Starsavior-master."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from starsavior_trainer.models import SkillOption
from starsavior_trainer.profile_loader import ProfileLoadError, load_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_ROOT = PROJECT_ROOT / "config" / "profiles"

BUILD_TO_SKILL_PROFILE = {
    "balanced": "default",
    "power_focus": "attack",
    "focus_focus": "speed",
    "durability_focus": "survival",
    "stamina_tank": "survival",
    "protection_focus": "survival",
}


@dataclass(frozen=True)
class SkillProfileEntry:
    name: str
    priority: int
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class SkillProfile:
    name: str
    entries: tuple[SkillProfileEntry, ...]

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "SkillProfile":
        entries: list[SkillProfileEntry] = []
        for raw in data.get("skills", []):
            if not isinstance(raw, dict):
                continue
            skill_name = str(raw.get("name", "")).strip()
            keywords = tuple(str(keyword).strip() for keyword in raw.get("keywords", []) if str(keyword).strip())
            if not skill_name or not keywords:
                continue
            try:
                priority = int(raw.get("priority", 0))
            except (TypeError, ValueError):
                priority = 0
            entries.append(SkillProfileEntry(name=skill_name, priority=priority, keywords=keywords))
        entries.sort(key=lambda entry: entry.priority, reverse=True)
        return cls(name=name, entries=tuple(entries))


@dataclass(frozen=True)
class SkillProfileChoice:
    option: SkillOption
    skill_name: str
    priority: int
    keyword: str
    score: float


def skill_profile_name_for_build(build_profile: str) -> str:
    return BUILD_TO_SKILL_PROFILE.get(build_profile, build_profile if build_profile in {"attack", "speed", "survival"} else "default")


def load_skill_profile(root: Path | str = DEFAULT_PROFILE_ROOT, profile_name: str = "default") -> SkillProfile:
    try:
        record = load_profile(root, "skills", profile_name)
    except ProfileLoadError:
        if profile_name == "default":
            raise
        record = load_profile(root, "skills", "default")
        profile_name = "default"
    return SkillProfile.from_dict(profile_name, record.data)


def choose_skill_by_profile(
    options: Iterable[SkillOption],
    profile: SkillProfile,
) -> SkillProfileChoice | None:
    best: SkillProfileChoice | None = None
    for option in options:
        if option.target is None:
            continue
        text = f"{option.name} {option.effect or ''}"
        if _already_learned(text):
            continue
        for entry in profile.entries:
            keyword = _matching_keyword(text, entry)
            if keyword is None:
                continue
            score = entry.priority * 100
            if option.cost is not None:
                score -= option.cost / 100
            choice = SkillProfileChoice(
                option=option,
                skill_name=entry.name,
                priority=entry.priority,
                keyword=keyword,
                score=score,
            )
            if best is None or choice.score > best.score:
                best = choice
            break
    return best


def _matching_keyword(text: str, entry: SkillProfileEntry) -> str | None:
    for keyword in entry.keywords:
        if keyword in text:
            return keyword
    return None


def _already_learned(text: str) -> bool:
    lowered = text.lower()
    return "已习得" in text or "learned" in lowered
