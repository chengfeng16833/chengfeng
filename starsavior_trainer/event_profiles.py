"""Event decision profiles migrated from Starsavior-master."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from starsavior_trainer.models import EventOption
from starsavior_trainer.profile_loader import ProfileLoadError, load_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_ROOT = PROJECT_ROOT / "config" / "profiles"

BUILD_TO_EVENT_PROFILE = {
    "balanced": "default",
    "power_focus": "attack",
    "focus_focus": "speed",
    "durability_focus": "survival",
    "stamina_tank": "survival",
    "protection_focus": "survival",
}


@dataclass(frozen=True)
class EventProfileOption:
    index: int
    keyword: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class EventProfileEntry:
    id: str
    event_name: str
    status: str
    recommended_option: int
    options: tuple[EventProfileOption, ...]


@dataclass(frozen=True)
class EventProfile:
    name: str
    events: tuple[EventProfileEntry, ...]

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "EventProfile":
        events: list[EventProfileEntry] = []
        for raw in data.get("events", []):
            if not isinstance(raw, dict):
                continue
            options: list[EventProfileOption] = []
            for raw_option in raw.get("options", []):
                if not isinstance(raw_option, dict):
                    continue
                try:
                    index = int(raw_option.get("index", 0))
                except (TypeError, ValueError):
                    index = 0
                keyword = str(raw_option.get("keyword", "")).strip()
                aliases = tuple(str(alias).strip() for alias in raw_option.get("alias", []) if str(alias).strip())
                if index > 0 and (keyword or aliases):
                    options.append(EventProfileOption(index=index, keyword=keyword, aliases=aliases))
            try:
                recommended = int(raw.get("recommended_option", 0))
            except (TypeError, ValueError):
                recommended = 0
            events.append(
                EventProfileEntry(
                    id=str(raw.get("id", "")).strip(),
                    event_name=str(raw.get("event_name", "")).strip(),
                    status=str(raw.get("status", "")).strip(),
                    recommended_option=recommended,
                    options=tuple(options),
                )
            )
        return cls(name=name, events=tuple(events))


@dataclass(frozen=True)
class EventProfileChoice:
    option: EventOption
    event_id: str
    event_name: str
    recommended_option: int
    keyword: str
    score: float


def event_profile_name_for_build(build_profile: str) -> str:
    if build_profile in {"attack", "speed", "survival"}:
        return build_profile
    return BUILD_TO_EVENT_PROFILE.get(build_profile, "default")


def load_event_profile(root: Path | str = DEFAULT_PROFILE_ROOT, profile_name: str = "default") -> EventProfile:
    try:
        record = load_profile(root, "events", profile_name)
    except ProfileLoadError:
        if profile_name == "default":
            raise
        record = load_profile(root, "events", "default")
        profile_name = "default"
    return EventProfile.from_dict(profile_name, record.data)


def choose_event_by_profile(
    options: Iterable[EventOption],
    profile: EventProfile,
) -> EventProfileChoice | None:
    options_tuple = tuple(options)
    if not options_tuple:
        return None
    best: tuple[float, EventProfileEntry, str] | None = None
    title = options_tuple[0].event_title
    for event in profile.events:
        if event.status != "confirmed" or event.recommended_option <= 0:
            continue
        score, keyword = _event_match_score(event, options_tuple, title)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, event, keyword)
    if best is None:
        return None
    score, event, keyword = best
    if not (1 <= event.recommended_option <= len(options_tuple)):
        return None
    return EventProfileChoice(
        option=options_tuple[event.recommended_option - 1],
        event_id=event.id,
        event_name=event.event_name,
        recommended_option=event.recommended_option,
        keyword=keyword,
        score=score,
    )


def _event_match_score(
    event: EventProfileEntry,
    options: tuple[EventOption, ...],
    title: str,
) -> tuple[float, str]:
    if title and event.event_name:
        title_score = _char_score(event.event_name, title)
        if title_score >= 0.6:
            return 100.0 + title_score, event.event_name

    best_score = 0.0
    best_keyword = ""
    for option in options:
        text = option.text
        for profile_option in event.options:
            for keyword in (profile_option.keyword, *profile_option.aliases):
                if not keyword:
                    continue
                score = _keyword_score(keyword, text)
                if score > best_score:
                    best_score = score
                    best_keyword = keyword
    return best_score, best_keyword


def _keyword_score(keyword: str, text: str) -> float:
    if keyword in text:
        return 10.0 + len(keyword) / 100
    char_score = _char_score(keyword, text)
    return char_score if char_score >= 0.75 else 0.0


def _char_score(needle: str, haystack: str) -> float:
    chars = [ch for ch in needle if "\u4e00" <= ch <= "\u9fff"]
    if not chars:
        return 0.0
    return sum(1 for ch in chars if ch in haystack) / len(chars)
