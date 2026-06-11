"""Training rule profiles migrated from Starsavior-master."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from starsavior_trainer.models import TrainingChoice
from starsavior_trainer.profile_loader import ProfileLoadError, load_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_ROOT = PROJECT_ROOT / "config" / "profiles"

BUILD_TO_TRAINING_PROFILE = {
    "balanced": "default",
    "power_focus": "attack",
    "focus_focus": "speed",
    "durability_focus": "survival",
    "stamina_tank": "survival",
    "protection_focus": "survival",
}

MASTER_STAT_TO_LOCAL = {
    "strength": "power",
    "stamina": "stamina",
    "agility": "wisdom",
    "focus": "speed",
    "guard": "guts",
}


@dataclass(frozen=True)
class TrainingRule:
    id: str
    field: str
    operator: str
    value: int | None
    action: str
    enabled: bool = True


@dataclass(frozen=True)
class TrainingProfile:
    name: str
    build_direction: str
    fail_rate_threshold: int
    rules: tuple[TrainingRule, ...]

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "TrainingProfile":
        legacy = data.get("legacy_strategy", {})
        if not isinstance(legacy, dict):
            legacy = {}
        rules: list[TrainingRule] = []
        for raw in data.get("rules", []):
            if not isinstance(raw, dict):
                continue
            try:
                value = int(raw["value"]) if "value" in raw else None
            except (TypeError, ValueError):
                value = None
            rules.append(
                TrainingRule(
                    id=str(raw.get("id", "")),
                    field=str(raw.get("field", "")),
                    operator=str(raw.get("operator", "")),
                    value=value,
                    action=str(raw.get("action", "builtin_default")),
                    enabled=bool(raw.get("enabled", True)),
                )
            )
        return cls(
            name=name,
            build_direction=str(legacy.get("build_direction", "attack")),
            fail_rate_threshold=int(legacy.get("fail_rate_threshold", 30)),
            rules=tuple(rules),
        )


@dataclass(frozen=True)
class TrainingProfileDecision:
    kind: str
    choice: TrainingChoice | None
    rule_id: str


def training_profile_name_for_build(build_profile: str) -> str:
    if build_profile in {"attack", "speed", "survival"}:
        return build_profile
    return BUILD_TO_TRAINING_PROFILE.get(build_profile, "default")


def load_training_profile(root: Path | str = DEFAULT_PROFILE_ROOT, profile_name: str = "default") -> TrainingProfile:
    try:
        record = load_profile(root, "training", profile_name)
    except ProfileLoadError:
        if profile_name == "default":
            raise
        record = load_profile(root, "training", "default")
        profile_name = "default"
    return TrainingProfile.from_dict(profile_name, record.data)


def evaluate_training_profile(
    choices: Iterable[TrainingChoice],
    profile: TrainingProfile,
    *,
    include_fallback_rules: bool = True,
) -> TrainingProfileDecision | None:
    choices_tuple = tuple(choices)
    for rule in profile.rules:
        if not rule.enabled:
            continue
        if not include_fallback_rules and not rule.field:
            continue
        if rule.field and not _rule_matches(rule, choices_tuple, profile):
            continue
        decision = _decision_for_action(rule.action, choices_tuple, rule.id)
        if decision is not None:
            return decision
    return None


def _rule_matches(rule: TrainingRule, choices: tuple[TrainingChoice, ...], profile: TrainingProfile) -> bool:
    if rule.value is None:
        return True
    metric = _metric_value(rule.field, choices, profile)
    if metric is None:
        return False
    if rule.operator == ">":
        return metric > rule.value
    if rule.operator == ">=":
        return metric >= rule.value
    if rule.operator == "<":
        return metric < rule.value
    if rule.operator == "<=":
        return metric <= rule.value
    return False


def _metric_value(field: str, choices: tuple[TrainingChoice, ...], profile: TrainingProfile) -> int | None:
    if field == "any_fail_rate":
        priority = _priority_stat(profile)
        choice = _choice_by_name(choices, priority)
        return choice.fail_rate if choice is not None else None
    if field == "any_gain":
        known = [choice.stat_gain for choice in choices if choice.fail_rate is not None]
        return max(known) if known else None
    if field.endswith("_fail_rate"):
        choice = _choice_for_field(choices, field, "_fail_rate")
        return choice.fail_rate if choice is not None else None
    if field.endswith("_gain"):
        choice = _choice_for_field(choices, field, "_gain")
        return choice.stat_gain if choice is not None else None
    return None


def _decision_for_action(
    action: str,
    choices: tuple[TrainingChoice, ...],
    rule_id: str,
) -> TrainingProfileDecision | None:
    if action == "rest":
        return TrainingProfileDecision("rest", None, rule_id)
    if action == "train_best_gain":
        choice = _best_gain_choice(choices)
        return TrainingProfileDecision("train", choice, rule_id) if choice is not None else None
    if action.startswith("train_"):
        stat = action.removeprefix("train_")
        if stat in {"best_gain", "most_icons"}:
            return None
        choice = _choice_by_name(choices, MASTER_STAT_TO_LOCAL.get(stat, stat))
        return TrainingProfileDecision("train", choice, rule_id) if choice is not None else None
    if action == "builtin_default":
        return None
    return None


def _priority_stat(profile: TrainingProfile) -> str:
    return "stamina" if profile.build_direction == "survival" else "power"


def _choice_for_field(
    choices: tuple[TrainingChoice, ...],
    field: str,
    suffix: str,
) -> TrainingChoice | None:
    stat = field.removesuffix(suffix)
    return _choice_by_name(choices, MASTER_STAT_TO_LOCAL.get(stat, stat))


def _choice_by_name(choices: tuple[TrainingChoice, ...], name: str) -> TrainingChoice | None:
    return next((choice for choice in choices if choice.name == name), None)


def _best_gain_choice(choices: tuple[TrainingChoice, ...]) -> TrainingChoice | None:
    known = [choice for choice in choices if choice.fail_rate is not None]
    if not known:
        return None
    return max(known, key=lambda choice: choice.stat_gain)
