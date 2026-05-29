from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starsavior_trainer.models import (
    CommissionOption,
    BlessingChoice,
    BlessingOption,
    BlessingSetup,
    BlessingSlot,
    CharacterOption,
    CharacterSelect,
    EventOption,
    GameState,
    ConfirmDialog,
    DialogueScene,
    EventFastForwardSetting,
    JourneyStart,
    Observation,
    Rect,
    RelicChoice,
    RelicOption,
    RestSubmenu,
    Screen,
    ShopItem,
    TrainingChoice,
)


def load_manifest(path: str | Path) -> tuple[GameState, list[Observation]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_state = data.get("state", {})
    state = GameState(
        current_rank=str(raw_state.get("current_rank", "C")),
        coins=int(raw_state.get("coins", 0)),
        safe_mode=bool(raw_state.get("safe_mode", True)),
    )

    observations = [_parse_observation(frame) for frame in data.get("frames", [])]
    return state, observations


def _parse_observation(raw: dict[str, Any]) -> Observation:
    screen = Screen(str(raw.get("screen", Screen.UNKNOWN.value)))
    confidence = float(raw.get("confidence", 1.0))
    source = raw.get("image") or raw.get("source")
    payload = _parse_payload(screen, raw.get("payload"))
    return Observation(screen=screen, confidence=confidence, payload=payload, source=str(source) if source else None)


def _parse_payload(screen: Screen, raw: Any) -> object | None:
    if raw is None:
        return None
    if screen == Screen.TRAINING_SELECT:
        return [
            TrainingChoice(
                name=str(item["name"]),
                stat_gain=int(item["stat_gain"]),
                ring=str(item.get("ring", "none")),
                fail_rate=(int(item["fail_rate"]) if item.get("fail_rate") is not None else None),
                target=_rect(item["target"]),
            )
            for item in raw
        ]
    if screen == Screen.REST_SUBMENU:
        return RestSubmenu(
            coins=int(raw["coins"]),
            has_meditation_room=bool(raw.get("has_meditation_room", False)),
            meditation_room=_rect(raw["meditation_room"]),
            rough_sleep=_rect(raw["rough_sleep"]),
        )
    if screen == Screen.EVENT_CHOICE:
        return [EventOption(text=str(item["text"]), target=_rect(item["target"])) for item in raw]
    if screen == Screen.DIALOGUE:
        return DialogueScene(
            skip_button=_rect(raw["skip_button"]),
            variant=str(raw.get("variant", "default")),
            text_area=_rect(raw["text_area"]) if raw.get("text_area") else None,
        )
    if screen == Screen.CHARACTER_SELECT:
        return CharacterSelect(
            options=[
                CharacterOption(
                    name=str(item["name"]),
                    rank=str(item["rank"]) if item.get("rank") is not None else None,
                    stars=int(item["stars"]) if item.get("stars") is not None else None,
                    specialty=str(item["specialty"]) if item.get("specialty") is not None else None,
                    selected=bool(item.get("selected", False)),
                    target=_rect(item["target"]),
                )
                for item in raw.get("options", [])
            ],
            confirm_button=_rect(raw["confirm_button"]),
            selected_name=str(raw["selected_name"]) if raw.get("selected_name") else None,
        )
    if screen == Screen.BLESSING_SETUP:
        return BlessingSetup(
            slots=[
                BlessingSlot(
                    index=int(item["index"]),
                    occupied=bool(item.get("occupied", False)),
                    target=_rect(item["target"]),
                )
                for item in raw.get("slots", [])
            ],
            auto_equip_button=_rect(raw["auto_equip_button"]),
            confirm_button=_rect(raw["confirm_button"]),
            can_confirm=bool(raw.get("can_confirm", False)),
        )
    if screen == Screen.BLESSING_CHOICE:
        return BlessingChoice(
            options=[
                BlessingOption(
                    name=str(item["name"]),
                    attribute=str(item["attribute"]),
                    value=int(item["value"]) if item.get("value") is not None else None,
                    target=_rect(item["target"]),
                    sub_blessing_count=int(item.get("sub_blessing_count", 0)),
                    sub_blessing_names=tuple(str(name) for name in item.get("sub_blessing_names", [])),
                )
                for item in raw.get("options", [])
            ],
            confirm_button=_rect(raw["confirm_button"]) if raw.get("confirm_button") else None,
        )
    if screen == Screen.JOURNEY_START:
        return JourneyStart(
            start_button=_rect(raw["start_button"]),
            auto_journey_button=_rect(raw["auto_journey_button"]) if raw.get("auto_journey_button") else None,
            arcana_slots=[_rect(item) for item in raw.get("arcana_slots", [])],
        )
    if screen == Screen.CONFIRM_DIALOG:
        return ConfirmDialog(
            title=str(raw.get("title", "")),
            message=str(raw.get("message", "")),
            confirm_button=_rect(raw["confirm_button"]),
            cancel_button=_rect(raw["cancel_button"]) if raw.get("cancel_button") else None,
        )
    if screen == Screen.EVENT_FAST_FORWARD_SETTING:
        return EventFastForwardSetting(
            no_fast_forward_option=_rect(raw["no_fast_forward_option"]),
            watched_only_option=_rect(raw["watched_only_option"]),
            all_events_option=_rect(raw["all_events_option"]),
            confirm_button=_rect(raw["confirm_button"]),
            selected_mode=str(raw["selected_mode"]) if raw.get("selected_mode") else None,
        )
    if screen == Screen.RELIC_CHOICE:
        if isinstance(raw, dict):
            return RelicChoice(
                options=[
                    RelicOption(
                        name=str(item["name"]),
                        score=int(item["score"]) if item.get("score") is not None else None,
                        target=_rect(item["target"]),
                    )
                    for item in raw.get("options", [])
                ],
                confirm_button=_rect(raw["confirm_button"]) if raw.get("confirm_button") else None,
                fixed_name=str(raw["fixed_name"]) if raw.get("fixed_name") else None,
                selected_name=str(raw["selected_name"]) if raw.get("selected_name") else None,
            )
        return [
            RelicOption(
                name=str(item["name"]),
                score=int(item["score"]) if item.get("score") is not None else None,
                target=_rect(item["target"]),
            )
            for item in raw
        ]
    if screen == Screen.COMMISSION_SELECT:
        return [
            CommissionOption(
                name=str(item["name"]),
                rank=str(item["rank"]),
                has_red_text=bool(item.get("has_red_text", False)),
                target=_rect(item["target"]),
            )
            for item in raw
        ]
    if screen == Screen.SHOP:
        return [ShopItem(name=str(item["name"]), price=int(item["price"]), target=_rect(item["target"])) for item in raw]
    return raw


def _rect(value: list[int]) -> Rect:
    if len(value) != 4:
        raise ValueError("rect must be [x, y, width, height]")
    return Rect(int(value[0]), int(value[1]), int(value[2]), int(value[3]))
