from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable
from typing import Iterable

from PIL import Image

from starsavior_trainer.image_regions import crop_region
from starsavior_trainer.models import (
    BattleScene,
    BlessingChoice,
    BlessingOption,
    BlessingSetup,
    BlessingSlot,
    CharacterOption,
    CharacterSelect,
    ConfirmDialog,
    CommissionChoice,
    CommissionOption,
    DialogueScene,
    EventFastForwardSetting,
    EventOption,
    JourneyStart,
    Rect,
    RelicChoice,
    RelicOption,
    RestSubmenu,
    ShopItem,
    SkillOption,
    TrainingChoice,
    TrainingHubStatus,
)
from starsavior_trainer.ocr import OcrEngine, OcrResult
from starsavior_trainer.regions import RegionProfile
from starsavior_trainer.vision import BlueButtonDetector, RingColorDetector

ATTRIBUTE_ALIASES = {
    "power": ("\u529b\u91cf", "power"),
    "stamina": ("\u4f53\u529b", "\u8010\u529b", "stamina", "hp"),
    "guts": ("\u97e7\u6027", "\u4fdd\u62a4", "guts", "protection"),
    "wisdom": ("\u4e13\u6ce8", "\u667a\u529b", "focus", "wisdom"),
    "speed": ("\u901f\u5ea6", "speed"),
}

RELIC_NAME_ALIASES = {
    "soft_toy_friend": ("\u8f6f\u7ef5\u7ef5\u7684\u73a9\u5076\u670b\u53cb", "\u73a9\u5076\u670b\u53cb"),
    "annoying_cuckoo_clock": ("\u70e6\u4eba\u7684\u5e03\u8c37\u9e1f\u65f6\u949f", "\u5e03\u8c37\u9e1f\u65f6\u949f"),
    "balanced_scale": ("\u5e73\u8861\u7684\u5929\u79e4", "\u5929\u79e4"),
}

TRAINING_NAME_ALIASES = {
    "power": ("\u529b\u91cf\u8bad\u7ec3", "\u529b\u91cf", "power"),
    "stamina": ("\u4f53\u529b\u8bad\u7ec3", "\u4f53\u529b", "stamina"),
    "guts": ("\u97e7\u6027\u8bad\u7ec3", "\u97e7\u6027", "guts"),
    "wisdom": ("\u96c6\u4e2d\u8bad\u7ec3", "\u96c6\u4e2d", "\u4e13\u6ce8\u8bad\u7ec3", "\u4e13\u6ce8", "wisdom", "focus"),
    "speed": ("\u901f\u5ea6\u8bad\u7ec3", "\u901f\u5ea6", "\u4fdd\u62a4\u8bad\u7ec3", "\u4fdd\u62a4", "speed"),
}

REST_OPTION_ALIASES = {
    "meditation_room": ("\u51a5\u60f3\u5ba4", "meditation"),
    "rough_sleep": ("\u9732\u5bbf", "rough", "\u9732\u8425"),
    "free_sleep": ("\u514d\u8d39", "free"),
}

SHOP_ALIASES = {
    "advanced_training_book": ("\u9ad8\u7ea7\u8bad\u7ec3\u4e66", "advanced"),
    "stamina_potion": ("\u4f53\u529b\u836f", "stamina potion", "\u4f53\u529b"),
    "mood_candy": ("\u5fc3\u60c5\u7cd6", "mood candy", "\u5fc3\u60c5"),
}

OCR_REGION_NAME_HINTS = (
    "anchor",
    "count",
    "description",
    "difficulty",
    "distance",
    "label",
    "message",
    "name",
    "number",
    "record",
    "resource",
    "score",
    "stat",
    "status",
    "summary",
    "text",
    "title",
)


@dataclass(frozen=True)
class RegionText:
    name: str
    text: str
    confidence: float


class RegionOcrReader:
    def __init__(self, profile: RegionProfile, ocr: OcrEngine):
        self.profile = profile
        self.ocr = ocr

    def read_all(self, image: Image.Image, max_area: int | None = None) -> list[RegionText]:
        return self.read_where(image, lambda _name, _rect: True, max_area=max_area)

    def read_names(self, image: Image.Image, names: Iterable[str]) -> list[RegionText]:
        wanted = set(names)
        return self.read_where(image, lambda name, _rect: name in wanted)

    def read_prefixes(
        self,
        image: Image.Image,
        prefixes: Iterable[str],
        max_area: int | None = None,
    ) -> list[RegionText]:
        wanted = tuple(prefixes)
        return self.read_where(image, lambda name, _rect: name.startswith(wanted), max_area=max_area)

    def read_ocr_regions(self, image: Image.Image, max_area: int | None = None) -> list[RegionText]:
        return self.read_where(image, lambda name, _rect: looks_like_ocr_region(name), max_area=max_area)

    def read_where(
        self,
        image: Image.Image,
        predicate: Callable[[str, Rect], bool],
        max_area: int | None = None,
    ) -> list[RegionText]:
        results: list[RegionText] = []
        for name, rect in self.profile.regions.items():
            if max_area is not None and rect.width * rect.height > max_area:
                continue
            if not predicate(name, rect):
                continue
            ocr_result = self.ocr.read_text(crop_region(image, rect))
            results.append(_to_region_text(name, ocr_result))
        return results


def _to_region_text(name: str, result: OcrResult) -> RegionText:
    return RegionText(name=name, text=result.text, confidence=result.confidence)


def normalize_ocr_text(text: str) -> str:
    return (
        text.casefold()
        .replace("\u3000", " ")
        .replace("\uff05", "%")
        .replace("\uff0c", ",")
        .strip()
    )


def contains_any_text(text: str, candidates: Iterable[str]) -> bool:
    normalized = normalize_ocr_text(text)
    return any(normalize_ocr_text(candidate) in normalized for candidate in candidates)


def looks_like_ocr_region(name: str) -> bool:
    return any(hint in name for hint in OCR_REGION_NAME_HINTS)


def extract_character_name(text: str) -> str | None:
    """Extract a character name from noisy OCR output.

    Each character-list entry is OCR'd as a single string that includes rank
    badge digits/symbols and icon glyphs before the actual name.  The name is
    always the rightmost run of 2+ CJK characters (e.g. '双9 康 克莱儿' → '克莱儿').
    Falls back to a single-character run if nothing longer is found.
    """
    # Collect all runs of CJK Unified Ideographs (BMP block 一-鿿 + Extension A 㐀-䶿)
    cjk_runs = re.findall("[一-鿿㐀-䶿]+", text)
    meaningful = [run for run in cjk_runs if len(run) >= 2]
    if meaningful:
        return meaningful[-1]
    if cjk_runs:
        return cjk_runs[-1]
    return None


def parse_first_int(text: str) -> int | None:
    normalized = normalize_ocr_text(text)
    match = re.search(r"(?<![a-z])([0-9olis][0-9olis,]*)(?![a-z])", normalized)
    if match is None:
        return None
    return _ocr_int_token_to_int(match.group(1))


def parse_last_int(text: str) -> int | None:
    normalized = normalize_ocr_text(text)
    matches = re.findall(r"(?<![a-z])([0-9olis][0-9olis,]*)(?![a-z])", normalized)
    if not matches:
        return None
    return _ocr_int_token_to_int(matches[-1])


def parse_percent(text: str) -> int | None:
    normalized = normalize_ocr_text(text)
    match = re.search(r"(?<![a-z])([0-9olis][0-9olis,]*)\s*%", normalized)
    if match is None:
        return parse_first_int(normalized)
    return _ocr_int_token_to_int(match.group(1))


def parse_attribute_value(text: str) -> tuple[str, int] | None:
    value = parse_first_int(text)
    if value is None:
        return None
    normalized = normalize_ocr_text(text)
    for attribute, aliases in ATTRIBUTE_ALIASES.items():
        if contains_any_text(normalized, aliases):
            return attribute, value
    return None


# ---------------------------------------------------------------------------
# Screen-specific parsers
# ---------------------------------------------------------------------------


def parse_character_select(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> CharacterSelect | None:
    """Build a character-select payload including the right-panel character list.

    Parses up to 7 character slots (character_option_1 \u2026 character_option_7)
    from the right-side scrollable list.  Character names are extracted from
    noisy OCR output via extract_character_name().  The currently highlighted
    character is identified from the left-panel OCR (character_selected_name).
    """
    texts = {item.name: item.text for item in region_texts}
    confirm_button = profile.regions.get("character_select_button")
    if confirm_button is None:
        return None

    title = texts.get("character_select_anchor_title", "")
    selected_name = _or_none(texts.get("character_selected_name"))
    if not selected_name and not contains_any_text(title, ("\u65c5\u7a0b\u8d77\u70b9", "journey")):
        return None

    # Build option list from the right-panel character slots
    options: list[CharacterOption] = []
    for i in range(1, 8):
        slot_name = f"character_option_{i}"
        rect = profile.regions.get(slot_name)
        if rect is None:
            continue
        raw_text = texts.get(slot_name, "")
        name = extract_character_name(raw_text) if raw_text else None
        if name is None:
            continue
        options.append(
            CharacterOption(
                name=name,
                rank=None,
                stars=None,
                specialty=None,
                selected=(name == selected_name),
                target=rect,
            )
        )

    # Always include the selected character from the left panel so the policy
    # can confirm even when the list OCR misses the highlighted entry.
    selected_target = profile.regions.get("character_selected_name") or confirm_button
    selected_option = CharacterOption(
        name=selected_name or "selected_character",
        rank=_or_none(texts.get("character_selected_rarity_area")),
        stars=None,
        specialty=_or_none(texts.get("character_selected_specialty")),
        selected=True,
        target=selected_target,
    )
    if not any(opt.name == selected_option.name for opt in options):
        options.insert(0, selected_option)

    # Determine whether the list can still be scrolled: we assume yes unless
    # fewer than 7 slots had recognisable names (list end reached).
    can_scroll = sum(1 for opt in options if opt.target != selected_target) >= 7

    return CharacterSelect(
        options=options,
        confirm_button=confirm_button,
        selected_name=selected_option.name,
        can_scroll=can_scroll,
    )


def parse_blessing_setup(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> BlessingSetup | None:
    """Build blessing setup payload from slot/button regions."""
    texts = {item.name: item.text for item in region_texts}
    confirm_button = profile.regions.get("blessing_confirm_button")
    auto_equip_button = profile.regions.get("blessing_auto_equip_button")
    if confirm_button is None or auto_equip_button is None:
        return None

    title = texts.get("blessing_setup_anchor_title", "")
    if not contains_any_text(title, ("\u65c5\u7a0b\u8d77\u70b9", "journey")) and not (
        profile.regions.get("blessing_slot_1") and profile.regions.get("blessing_slot_2")
    ):
        return None

    can_confirm = _is_blue_region(confirm_button, image)
    slots: list[BlessingSlot] = []
    for index in (1, 2):
        rect = profile.regions.get(f"blessing_slot_{index}")
        if rect is not None:
            slots.append(BlessingSlot(index=index, occupied=_is_blessing_slot_filled(rect, image), target=rect))

    if not slots:
        return None
    return BlessingSetup(
        slots=slots,
        auto_equip_button=auto_equip_button,
        confirm_button=confirm_button,
        can_confirm=can_confirm,
    )


def parse_blessing_choice(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> BlessingChoice | None:
    """Read visible blessing cards and their main attribute values.

    Uses the right-side detail panel OCR to cross-validate which card is
    currently selected, falling back to visual border-detection.
    """
    texts = {item.name: item.text for item in region_texts}
    title = texts.get("blessing_choice_anchor_archive", "")
    if not contains_any_text(title, ("\u661f\u8fb0\u6863\u6848", "archive")) and not any(
        name.startswith("blessing_card_") for name in texts
    ):
        return None

    # ── detail-panel OCR: read the selected blessing's attribute+value ──
    detail_parsed = _parse_detail_panel_selection(texts)
    detail_attribute, detail_value = detail_parsed if detail_parsed else (None, None)

    # ── visual selected-card detection (fallback) ──
    visual_selected_index = _selected_blessing_card_index(profile, image)

    # ── read sub-blessing count from detail panel ──
    selected_sub_blessing_count = _count_detail_sub_blessings(profile, image)

    # ── build options from card-grid OCR ──
    options: list[BlessingOption] = []
    ocr_selected_index: int | None = None

    for index in range(1, 21):
        card_key = f"blessing_card_{index:02d}"
        target = profile.regions.get(card_key)
        if target is None:
            continue
        parsed = parse_attribute_value(texts.get(f"{card_key}_attribute", ""))
        if parsed is None:
            continue
        attribute, value = parsed

        # Cross-check: does this card match the detail panel?
        if ocr_selected_index is None and detail_attribute == attribute and detail_value == value:
            ocr_selected_index = index

        options.append(
            BlessingOption(
                name=f"{attribute}_blessing_{value}_{index:02d}",
                attribute=attribute,
                value=value,
                target=target,
                sub_blessing_count=0,  # patched below after selection is resolved
            )
        )

    # ── OCR recovery: if detail panel found a selection but no card OCR matched,
    #     rebuild the selected card entry from detail-panel data + visual index. ──
    if (
        not options
        and detail_parsed is not None
        and visual_selected_index is not None
        and profile.regions.get(f"blessing_card_{visual_selected_index:02d}") is not None
    ):
        attribute, value = detail_parsed
        card_key = f"blessing_card_{visual_selected_index:02d}"
        options.append(
            BlessingOption(
                name=f"{attribute}_blessing_{value}_{visual_selected_index:02d}",
                attribute=attribute,
                value=value,
                target=profile.regions[card_key],
                sub_blessing_count=selected_sub_blessing_count,
            )
        )
        ocr_selected_index = visual_selected_index

    if not options:
        return None

    # ── resolve selected index: OCR detail panel > visual highlight > None ──
    selected_card_index = ocr_selected_index or visual_selected_index

    # Patch sub_blessing_count only when OCR confirms which card the detail panel is showing.
    # Visual-only selection (no OCR detail match) leaves sub_blessing_count=0; the
    # BlessingChoiceInspector handles explicit per-card inspection in the live loop.
    if ocr_selected_index is not None:
        for i, option in enumerate(options):
            if option.name.endswith(f"_{ocr_selected_index:02d}"):
                options[i] = BlessingOption(
                    name=option.name,
                    attribute=option.attribute,
                    value=option.value,
                    target=option.target,
                    sub_blessing_count=selected_sub_blessing_count,
                )
                break

    return BlessingChoice(
        options=options,
        confirm_button=profile.regions.get("blessing_choice_confirm_button"),
        selected_name=next(
            (option.name for option in options if option.name.endswith(f"_{selected_card_index:02d}")), None
        )
        if selected_card_index is not None
        else None,
        detail_sub_blessing_count=selected_sub_blessing_count,
    )


def _parse_detail_panel_selection(texts: dict[str, str]) -> tuple[str, int] | None:
    """Parse the currently selected blessing attribute+value from the right-side detail panel OCR.

    Checks multiple region names to accommodate different profile naming conventions
    (e.g. ``blessing_choice_detail_type`` vs ``blessing_choice_detail_attribute``).
    """
    for region_name in (
        "blessing_choice_detail_type",
        "blessing_choice_detail_attribute",
    ):
        raw = texts.get(region_name, "")
        if raw.strip():
            parsed = parse_attribute_value(raw)
            if parsed is not None:
                return parsed
    return None


def parse_journey_start(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> JourneyStart | None:
    texts = {item.name: item.text for item in region_texts}
    start_button = profile.regions.get("journey_start_button")
    if start_button is None:
        return None
    arcana_slots = [
        rect
        for index in range(1, 6)
        if (rect := profile.regions.get(f"journey_start_arcana_slot_{index}")) is not None
    ]
    return JourneyStart(
        start_button=start_button,
        auto_journey_button=profile.regions.get("journey_start_auto_journey_button"),
        arcana_slots=arcana_slots,
    )


def parse_confirm_dialog(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> ConfirmDialog | None:
    texts = {item.name: item.text for item in region_texts}
    confirm_button = profile.regions.get("confirm_dialog_confirm_button")
    if confirm_button is None:
        return None
    title = _or_none(texts.get("confirm_dialog_title")) or "confirm_dialog"
    message = _or_none(texts.get("confirm_dialog_message")) or ""
    has_dialog_regions = any(name.startswith("confirm_dialog") for name in texts)
    if title == "confirm_dialog" and not message and not has_dialog_regions:
        return None
    return ConfirmDialog(
        title=title,
        message=message,
        confirm_button=confirm_button,
        cancel_button=profile.regions.get("confirm_dialog_cancel_button"),
    )


def parse_event_fast_forward_setting(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> EventFastForwardSetting | None:
    texts = {item.name: item.text for item in region_texts}
    no_option = profile.regions.get("event_fast_forward_no_option")
    watched_option = profile.regions.get("event_fast_forward_watched_option")
    all_option = profile.regions.get("event_fast_forward_all_option")
    confirm_button = profile.regions.get("event_fast_forward_confirm_button")
    if no_option is None or watched_option is None or all_option is None or confirm_button is None:
        return None

    title = texts.get("event_fast_forward_title", "")
    if title and not contains_any_text(title, ("\u4e8b\u4ef6\u5feb\u8f6c\u8bbe\u5b9a", "fast")):
        return None

    selected_mode = None
    if image is not None:
        checkbox_modes = (
            ("event_fast_forward_no_checkbox", "no_fast_forward"),
            ("event_fast_forward_watched_checkbox", "watched_only"),
            ("event_fast_forward_all_checkbox", "all_events"),
        )
        for region_name, mode in checkbox_modes:
            rect = profile.regions.get(region_name)
            if rect is not None and _is_blue_region(rect, image):
                selected_mode = mode
                break

    return EventFastForwardSetting(
        no_fast_forward_option=no_option,
        watched_only_option=watched_option,
        all_events_option=all_option,
        confirm_button=confirm_button,
        selected_mode=selected_mode,
    )


def parse_dialogue_scene(region_texts: Iterable[RegionText], profile: RegionProfile) -> DialogueScene | None:
    """Build a dialogue payload from OCR anchors and skip-button candidates."""

    texts = {item.name: item.text for item in region_texts}

    intro_skip = profile.regions.get("dialogue_intro_skip_button")
    if intro_skip is not None and (
        contains_any_text(texts.get("dialogue_intro_skip_button", ""), ("skip", "\u8df3\u8fc7"))
        or contains_any_text(texts.get("dialogue_intro_location_text", ""), ("\u89c2\u6d4b\u673a\u6784", "noa"))
    ):
        return DialogueScene(
            skip_button=intro_skip,
            variant="intro_story",
            text_area=profile.regions.get("dialogue_intro_text_area"),
        )

    journey_skip = profile.regions.get("dialogue_journey_skip_button")
    if journey_skip is not None and _has_journey_dialogue_anchor(texts):
        return DialogueScene(
            skip_button=journey_skip,
            variant="journey_hud",
            text_area=profile.regions.get("dialogue_journey_text_area"),
        )

    for name, rect in profile.regions.items():
        if name.startswith("dialogue_") and name.endswith("_skip_button"):
            if contains_any_text(texts.get(name, ""), ("skip", "\u8df3\u8fc7")):
                return DialogueScene(skip_button=rect, variant=name.removeprefix("dialogue_").removesuffix("_skip_button"))

    return None


def parse_relic_choice(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> RelicChoice | None:
    texts = {item.name: item.text for item in region_texts}
    if not _has_relic_choice_anchor(texts):
        return None

    options: list[RelicOption] = []
    for index in range(1, 4):
        key = f"relic_choice_card_{index}"
        target = profile.regions.get(key)
        if target is None:
            continue
        name = parse_relic_name(texts.get(f"{key}_name", ""))
        score = parse_first_int(texts.get(f"{key}_score", ""))
        if name is not None or score is not None:
            options.append(RelicOption(name=name or f"unknown_relic_{index}", score=score, target=target))

    if not options:
        return None

    fixed_name = "annoying_cuckoo_clock" if _is_initial_relic_choice(texts, options) else None
    selected_name = fixed_name if fixed_name and _is_confirm_button_active(profile, image) else None

    return RelicChoice(
        options=options,
        confirm_button=profile.regions.get("relic_choice_confirm_button"),
        fixed_name=fixed_name,
        selected_name=selected_name,
    )


def parse_relic_name(text: str) -> str | None:
    for name, aliases in RELIC_NAME_ALIASES.items():
        if contains_any_text(text, aliases):
            return name
    return None


# ---------------------------------------------------------------------------
# Training Hub parser
# ---------------------------------------------------------------------------


def parse_training_hub(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> TrainingHubStatus | None:
    """Recognize the training hub screen and extract status information."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_training_hub_anchor(texts, profile):
        return None

    turn_label = _or_none(texts.get("training_hub_turn_label"))
    rank_label = _or_none(texts.get("training_hub_rank_label"))
    coins = parse_first_int(texts.get("training_hub_coin_count", ""))
    potential_points = parse_first_int(texts.get("training_hub_potential_points", ""))
    alert_text = texts.get("training_hub_commission_alert", "")
    has_commission_alert = contains_any_text(alert_text, ("\u53d7\u7406", "\u8ba8\u4f10", "\u59d4\u6258", "commission"))
    alert_rect = profile.regions.get("training_hub_commission_alert")
    if not has_commission_alert and alert_rect is not None and image is not None:
        has_commission_alert = _detect_red_text(crop_region(image, alert_rect))
    shop_alert_text = texts.get("training_hub_shop_alert", "")
    has_shop_alert = contains_any_text(shop_alert_text, ("\u5546\u54c1", "\u5230\u8d27", "\u4ea4\u6613", "shop"))
    shop_alert_rect = profile.regions.get("training_hub_shop_alert")
    if not has_shop_alert and shop_alert_rect is not None and image is not None:
        has_shop_alert = _detect_yellow_text(crop_region(image, shop_alert_rect))
    can_learn_skill = contains_any_text(
        texts.get("training_hub_skill_available", ""),
        ("\u53ef\u4e60\u5f97", "\u4e60\u5f97", "learn"),
    )

    return TrainingHubStatus(
        turn_label=turn_label,
        coins=coins,
        rank_label=rank_label,
        potential_points=potential_points,
        training_button=profile.regions.get("training_hub_action_training"),
        commission_button=profile.regions.get("training_hub_action_commission"),
        rest_button=profile.regions.get("training_hub_action_rest"),
        skill_button=profile.regions.get("training_hub_nav_potential"),
        shop_button=profile.regions.get("training_hub_action_shop"),
        has_commission_alert=has_commission_alert,
        has_shop_alert=has_shop_alert,
        can_learn_skill=can_learn_skill,
    )


def _has_training_hub_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    training_btn = profile.regions.get("training_hub_action_training")
    commission_btn = profile.regions.get("training_hub_action_commission")
    rest_btn = profile.regions.get("training_hub_action_rest")
    if training_btn is None or commission_btn is None or rest_btn is None:
        return False
    title = texts.get("training_hub_anchor_title", "")
    distance = texts.get("training_hub_distance", "")
    turn = texts.get("training_hub_turn_label", "")
    actions = " ".join(
        texts.get(name, "")
        for name in (
            "training_hub_action_training",
            "training_hub_action_commission",
            "training_hub_action_shop",
            "training_hub_action_rest",
            "training_hub_nav_potential",
        )
    )
    return contains_any_text(
        title + distance + turn + actions,
        (
            "\u8ddd\u79bb\u76ee\u6807",
            "\u53c2\u52a0",
            "\u65c5\u7a0b",
            "\u8bad\u7ec3",
            "\u59d4\u6258",
            "\u4ea4\u6613",
            "\u4f11\u606f",
            "\u6f5c\u8d28",
        ),
    )


# ---------------------------------------------------------------------------
# Training Select parser
# ---------------------------------------------------------------------------

TRAINING_CARD_ATTRIBUTES = ("power", "stamina", "guts", "wisdom", "speed")


def parse_training_select(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> list[TrainingChoice] | None:
    """Read the five training options from the training-select screen."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_training_select_anchor(texts, profile):
        return None

    confirm_button = profile.regions.get("training_select_confirm_button")

    choices: list[TrainingChoice] = []
    for attr in TRAINING_CARD_ATTRIBUTES:
        card_rect = profile.regions.get(f"training_select_card_{attr}")
        if card_rect is None:
            continue

        card_text = texts.get(f"training_select_card_{attr}", "")
        name_text = texts.get(f"training_select_card_{attr}_name", "")
        fail_text = texts.get(f"training_select_card_{attr}_fail_rate", "")
        gain_text = texts.get(f"training_select_stat_gain_{attr}", "")

        recognized_name = _match_training_name(name_text) or _match_training_name(card_text) or attr
        # Fail rate must be a percentage; never fall back to a bare integer so
        # decorative digits inside the card box are not mistaken for a fail rate.
        card_fail = _parse_fail_rate(fail_text)
        if card_fail is None:
            card_fail = _parse_fail_rate(card_text)
        # The failure rate is only rendered on the currently highlighted card, so
        # its presence is a reliable "this card is selected" signal.
        selected = card_fail is not None
        fail_rate = card_fail or 0
        stat_gain = parse_first_int(gain_text) or 0

        ring = "none"
        if image is not None:
            ring_rect = profile.regions.get("training_select_ring_detect")
            if ring_rect is not None:
                ring_signal = RingColorDetector().detect(crop_region(image, ring_rect))
                ring = ring_signal.name

        choices.append(
            TrainingChoice(
                name=recognized_name,
                stat_gain=stat_gain,
                ring=ring,
                fail_rate=fail_rate,
                target=card_rect,
                selected=selected,
                confirm_button=confirm_button,
            )
        )

    if not choices:
        return None
    return choices


def _has_training_select_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    confirm = profile.regions.get("training_select_confirm_button")
    if confirm is None:
        return False
    for attr in TRAINING_CARD_ATTRIBUTES:
        name_text = texts.get(f"training_select_card_{attr}_name", "") or texts.get(f"training_select_card_{attr}", "")
        if _match_training_name(name_text) is not None:
            return True
    return False


def _match_training_name(text: str) -> str | None:
    for name, aliases in TRAINING_NAME_ALIASES.items():
        if contains_any_text(text, aliases):
            return name
    return None


def _parse_fail_rate(text: str) -> int | None:
    """Parse a failure-rate percentage, requiring an explicit '%' sign.

    Unlike parse_percent, this never falls back to a bare integer, so decorative
    digits or icon glyphs inside a training card are not read as a fail rate.
    """
    if not text or not text.strip():
        return None
    normalized = normalize_ocr_text(text)
    match = re.search(r"([0-9olis][0-9olis,]*)\s*%", normalized)
    if match is None:
        return None
    return _ocr_int_token_to_int(match.group(1))


# ---------------------------------------------------------------------------
# Rest Submenu parser
# ---------------------------------------------------------------------------


def parse_rest_submenu(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> RestSubmenu | None:
    """Read the rest submenu with coin count and sleep options."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_rest_submenu_anchor(texts, profile):
        return None

    coins = parse_first_int(texts.get("rest_submenu_coin_count", "")) or 0

    meditation_rect = profile.regions.get("rest_submenu_option_3")
    rough_sleep_rect = profile.regions.get("rest_submenu_option_1")
    free_sleep_rect = profile.regions.get("rest_submenu_option_1")

    meditation_label = texts.get("rest_submenu_option_3_label", "")
    meditation_option_text = texts.get("rest_submenu_option_3", "")
    has_any_rest_ocr = any(name.startswith("rest_submenu_") and text.strip() for name, text in texts.items())
    has_meditation = meditation_rect is not None and (
        contains_any_text(meditation_label, REST_OPTION_ALIASES["meditation_room"])
        or contains_any_text(meditation_option_text, REST_OPTION_ALIASES["meditation_room"])
        or not has_any_rest_ocr
    )

    return RestSubmenu(
        coins=coins,
        has_meditation_room=has_meditation,
        meditation_room=meditation_rect or rough_sleep_rect or Rect(0, 0, 1, 1),
        rough_sleep=rough_sleep_rect or free_sleep_rect or Rect(0, 0, 1, 1),
    )


def _has_rest_submenu_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    for key in ("rest_submenu_option_1", "rest_submenu_option_2", "rest_submenu_option_3"):
        if profile.regions.get(key) is None:
            return False
    return True


# ---------------------------------------------------------------------------
# Event Choice parser
# ---------------------------------------------------------------------------


def parse_event_choice(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> list[EventOption] | None:
    """Read event choice options from the screen."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_event_choice_anchor(texts, profile):
        return None

    event_title = texts.get("event_choice_title", "").strip()
    options: list[EventOption] = []
    for idx in range(1, 5):
        target = profile.regions.get(f"event_choice_option_{idx}")
        if target is None:
            continue
        option_text = texts.get(f"event_choice_option_{idx}_text", "") or texts.get(f"event_choice_option_{idx}", "")
        if option_text.strip():
            options.append(EventOption(text=option_text.strip(), target=target, event_title=event_title))

    if not options:
        return None
    return options


def _has_event_choice_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    title = texts.get("event_choice_title", "")
    option1 = texts.get("event_choice_option_1_text", "")
    if contains_any_text(title, ("\u65c5\u7a0b\u4e8b\u4ef6", "\u4e8b\u4ef6", "event")):
        return True
    if option1.strip() and profile.regions.get("event_choice_option_1") is not None:
        return True
    return False


# ---------------------------------------------------------------------------
# Commission Select parser
# ---------------------------------------------------------------------------


def parse_commission_select(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> CommissionChoice | None:
    """Read commission options, including red-text suitability detection."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_commission_anchor(texts, profile):
        return None

    options: list[CommissionOption] = []
    for idx in range(1, 6):
        target = profile.regions.get(f"commission_select_option_{idx}")
        if target is None:
            continue
        name = texts.get(f"commission_select_option_{idx}_name", "").strip()
        rank = texts.get(f"commission_select_option_{idx}_rank", "").strip()
        if not name:
            continue

        has_red = False
        if image is not None:
            red_rect = profile.regions.get(f"commission_select_option_{idx}_red_text")
            if red_rect is not None:
                has_red = _detect_red_text(crop_region(image, red_rect))

        options.append(
            CommissionOption(
                name=name,
                rank=rank,
                has_red_text=has_red,
                target=target,
            )
        )

    if not options:
        return None
    accept_btn = profile.regions.get("commission_select_accept_button")
    back_btn = profile.regions.get("top_back_button")
    return CommissionChoice(options=options, accept_button=accept_btn, back_button=back_btn)


def _has_commission_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    title = texts.get("commission_select_anchor_title", "")
    names = " ".join(texts.get(f"commission_select_option_{i}_name", "") for i in range(1, 6))
    return bool(names.strip()) or contains_any_text(title, ("\u59d4\u6258", "commission"))


# ---------------------------------------------------------------------------
# Shop parser
# ---------------------------------------------------------------------------


def parse_shop(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> list[ShopItem] | None:
    """Read shop items with names and prices."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_shop_anchor(texts, profile):
        return None

    items: list[ShopItem] = []
    for idx in range(1, 6):
        target = profile.regions.get(f"shop_item_{idx}")
        if target is None:
            continue
        name = texts.get(f"shop_item_{idx}_name", "").strip()
        price = parse_first_int(texts.get(f"shop_item_{idx}_price", ""))
        if not name or price is None:
            continue

        button = profile.regions.get(f"shop_item_{idx}_button")
        click_target = button if button is not None else target

        items.append(ShopItem(name=name, price=price, target=click_target))

    if not items:
        return None
    return items


def _has_shop_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    names = " ".join(texts.get(f"shop_item_{i}_name", "") for i in range(1, 6))
    prices = " ".join(texts.get(f"shop_item_{i}_price", "") for i in range(1, 6))
    return bool(names.strip() + prices.strip())


# ---------------------------------------------------------------------------
# Region Move parser
# ---------------------------------------------------------------------------


def parse_region_move(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> Rect | None:
    """Detect the region-move screen and return the move button rect."""
    texts = {item.name: item.text for item in region_texts}

    move_rect = profile.regions.get("region_move_button")
    if move_rect is None:
        return None

    button_text = texts.get("region_move_button_text", "")
    if contains_any_text(button_text, ("\u79fb\u52a8", "move")):
        return move_rect

    return None


# ---------------------------------------------------------------------------
# Battle parser
# ---------------------------------------------------------------------------


def parse_battle(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
) -> BattleScene | None:
    """Detect battle screens and return the next battle action."""
    texts = {item.name: item.text for item in region_texts}

    action_button = profile.regions.get("battle_entry_button") or profile.regions.get("battle_skip_button")
    if action_button is None:
        return None

    skip_text = texts.get("battle_skip_button_text", "")
    title_text = texts.get("battle_title", "")
    has_skip = contains_any_text(skip_text, ("\u8df3\u8fc7\u6218\u6597", "\u8df3\u8fc7", "skip"))
    has_battle = contains_any_text(title_text, ("\u8bc4\u9274\u6218", "\u6218\u6597", "battle"))

    confirm_button = profile.regions.get("battle_accept_button") or profile.regions.get("battle_confirm_button")
    confirm_active = False
    if confirm_button is not None and image is not None:
        signal = BlueButtonDetector().detect(crop_region(image, confirm_button))
        confirm_active = signal.name == "active_blue"

    if not has_skip and not has_battle:
        if confirm_active:
            return BattleScene(
                skip_button=action_button,
                confirm_button=confirm_button,
                confirm_active=True,
            )
        if image is not None:
            signal = BlueButtonDetector().detect(crop_region(image, action_button))
            if signal.name != "active_blue":
                return None
        else:
            return None

    return BattleScene(
        skip_button=action_button,
        confirm_button=confirm_button,
        confirm_active=confirm_active,
    )


# ---------------------------------------------------------------------------
# Post-Training parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostTrainingResult:
    result_text: str | None = None
    stat_gain_value: int | None = None
    event_title: str | None = None
    skip_button: Rect | None = None


def parse_post_training(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> PostTrainingResult | None:
    """Read post-training result screen."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_post_training_anchor(texts, profile):
        return None

    result_text = (
        _or_none(texts.get("post_training_result_text"))
        or _or_none(texts.get("post_training_success_text"))
        or _or_none(texts.get("post_training_title"))
    )
    stat_gain = parse_first_int(texts.get("post_training_stat_gain_value", "")) or parse_first_int(
        texts.get("post_training_success_text", "")
    )
    event_title = _or_none(texts.get("post_training_event_title"))

    return PostTrainingResult(
        result_text=result_text,
        stat_gain_value=stat_gain,
        event_title=event_title,
        skip_button=profile.regions.get("post_training_continue_area") or profile.regions.get("post_training_skip_button"),
    )


def _has_post_training_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    result = texts.get("post_training_result_text", "")
    title = texts.get("post_training_title", "")
    success = texts.get("post_training_success_text", "")
    event = texts.get("post_training_event_title", "")
    gain = texts.get("post_training_stat_gain_value", "")
    combined = result + title + success + event + gain
    return contains_any_text(
        combined,
        ("\u63d0\u5347", "\u4e8b\u4ef6", "\u8bad\u7ec3\u6210\u529f", "\u8bad\u7ec3", "+", "event"),
    ) or parse_first_int(gain) is not None


# ---------------------------------------------------------------------------
# Training Direction parser
# ---------------------------------------------------------------------------


def parse_training_direction(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> list[EventOption] | None:
    """Read the fixed training-direction event options."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_training_direction_anchor(texts):
        return None

    options: list[EventOption] = []
    for idx in range(1, 4):
        target = profile.regions.get(f"training_direction_option_{idx}")
        if target is None:
            continue
        option_text = texts.get(f"training_direction_option_{idx}_text", "")
        if option_text.strip():
            options.append(EventOption(text=option_text.strip(), target=target))

    if not options:
        return None
    return options


def _has_training_direction_anchor(texts: dict[str, str]) -> bool:
    title = texts.get("training_direction_title", "")
    return contains_any_text(title, ("\u8bad\u7ec3\u7684\u65b9\u5411\u6027", "direction"))


# ---------------------------------------------------------------------------
# Skill Select parser
# ---------------------------------------------------------------------------


def parse_skill_select(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> list[SkillOption] | None:
    """Read skill selection options from the screen."""
    texts = {item.name: item.text for item in region_texts}

    if not _has_skill_select_anchor(texts, profile):
        return None

    options: list[SkillOption] = []
    for idx in range(1, 6):
        target = profile.regions.get(f"skill_select_option_{idx}_button") or profile.regions.get(f"skill_select_option_{idx}")
        if target is None:
            continue
        name = texts.get(f"skill_select_option_{idx}_name", "").strip()
        if not name:
            continue
        effect = texts.get(f"skill_select_option_{idx}_effect", "").strip() or None
        cost = parse_last_int(texts.get(f"skill_select_option_{idx}_cost", ""))
        if cost is None:
            cost = parse_last_int(texts.get(f"skill_select_option_{idx}_button", ""))
        options.append(SkillOption(name=name, effect=effect, cost=cost, target=target))

    if not options:
        return None
    return options


def _has_skill_select_anchor(texts: dict[str, str], profile: RegionProfile) -> bool:
    title = texts.get("skill_select_title", "")
    names = " ".join(texts.get(f"skill_select_option_{i}_name", "") for i in range(1, 6))
    return bool(names.strip()) or contains_any_text(title, ("\u6f5c\u8d28", "\u6280\u80fd", "skill"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_journey_dialogue_anchor(texts: dict[str, str]) -> bool:
    anchor_names = (
        "dialogue_journey_event_label",
        "dialogue_journey_title",
        "dialogue_journey_distance",
        "dialogue_journey_text_area",
    )
    anchor_text = " ".join(texts.get(name, "") for name in anchor_names)
    if texts.get("dialogue_journey_text_area", "").strip() and contains_any_text(
        texts.get("dialogue_journey_event_label", "") + texts.get("dialogue_journey_title", ""),
        ("\u4e8b\u4ef6",),
    ):
        return True
    return contains_any_text(
        anchor_text,
        (
            "\u65c5\u7a0b\u4e8b\u4ef6",
            "\u53c2\u52a0",
            "\u8ddd\u79bb\u76ee\u6807",
            "\u83b7\u5f97",
        ),
    )


def _has_relic_choice_anchor(texts: dict[str, str]) -> bool:
    if contains_any_text(texts.get("relic_choice_title", ""), ("\u9009\u62e9\u5956\u52b1",)):
        return True
    return any(parse_relic_name(texts.get(f"relic_choice_card_{index}_name", "")) for index in range(1, 4))


def _is_initial_relic_choice(texts: dict[str, str], options: list[RelicOption]) -> bool:
    if not contains_any_text(texts.get("relic_choice_title", ""), ("\u9009\u62e9\u5956\u52b1",)):
        return False
    names = {option.name for option in options}
    return {"soft_toy_friend", "annoying_cuckoo_clock", "balanced_scale"}.issubset(names)


def _is_confirm_button_active(profile: RegionProfile, image: Image.Image | None) -> bool:
    rect = profile.regions.get("relic_choice_confirm_button")
    if image is None or rect is None:
        return False
    return _is_blue_region(rect, image)


def _is_blue_region(rect: Rect, image: Image.Image | None) -> bool:
    if image is None:
        return False
    signal = BlueButtonDetector().detect(crop_region(image, rect))
    return signal.name == "active_blue"


def _is_blessing_slot_filled(rect: Rect, image: Image.Image | None) -> bool:
    if image is None:
        return False
    try:
        gray = crop_region(image, rect).convert("L")
        pixel_data = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
        pixels = list(pixel_data)
        if not pixels:
            return False
        mean = sum(pixels) / len(pixels)
        variance = sum((pixel - mean) ** 2 for pixel in pixels) / len(pixels)
        stddev = variance**0.5
        return mean >= 85 and stddev >= 45
    except Exception:
        return False


def _selected_blessing_card_index(profile: RegionProfile, image: Image.Image | None) -> int | None:
    if image is None:
        return None
    scores: list[tuple[float, int]] = []
    for index in range(1, 21):
        rect = profile.regions.get(f"blessing_card_{index:02d}")
        if rect is not None:
            scores.append((_card_highlight_score(rect, image), index))
    if not scores:
        return None
    scores.sort(reverse=True)
    best_score, best_index = scores[0]
    next_score = scores[1][0] if len(scores) > 1 else 0.0
    if best_score >= 0.09 and best_score >= next_score + 0.02:
        return best_index
    return None


def _card_highlight_score(rect: Rect, image: Image.Image) -> float:
    try:
        rgb = image.convert("RGB")
        iw, ih = rgb.size

        def _safe_crop(left: int, upper: int, right: int, lower: int) -> Image.Image:
            left = max(0, min(left, iw))
            upper = max(0, min(upper, ih))
            right = max(left + 1, min(right, iw))
            lower = max(upper + 1, min(lower, ih))
            return rgb.crop((left, upper, right, lower))

        outside_top = _safe_crop(rect.x - 10, rect.y - 10, rect.x + rect.width + 10, rect.y + 2)
        outside_left = _safe_crop(rect.x - 12, rect.y - 10, rect.x, rect.y + rect.height + 10)
        inside_left = _safe_crop(rect.x, rect.y + 20, rect.x + 15, rect.y + min(180, rect.height))
        return max(_bright_border_ratio(outside_top), _bright_border_ratio(outside_left), _bright_border_ratio(inside_left))
    except Exception:
        return 0.0


def _bright_border_ratio(image: Image.Image) -> float:
    pixel_data = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    pixels = list(pixel_data)
    if not pixels:
        return 0.0
    bright_border = sum(1 for r, g, b in pixels if r > 220 and g > 210 and b > 190)
    return bright_border / len(pixels)


def _count_detail_sub_blessings(profile: RegionProfile, image: Image.Image | None) -> int:
    if image is None:
        return 0
    count = 0
    for index in range(1, 4):
        rect = profile.regions.get(f"blessing_choice_detail_sub_{index}")
        if rect is not None and _detail_sub_blessing_slot_filled(rect, image):
            count += 1
    return count


def _detail_sub_blessing_slot_filled(rect: Rect, image: Image.Image) -> bool:
    try:
        rgb = crop_region(image, rect).convert("RGB")
        pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        pixels = list(pixel_data)
        if not pixels:
            return False
        visible_pixels = sum(1 for r, g, b in pixels if r + g + b > 220)
        return visible_pixels / len(pixels) >= 0.20
    except Exception:
        return False


def _detect_red_text(image: Image.Image) -> bool:
    """Crude red-text detection: check if enough red-ish pixels exist."""
    try:
        rgb = image.convert("RGB")
        pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        pixels = list(pixel_data)
        total = max(len(pixels), 1)
        red_count = 0
        for r, g, b in pixels:
            if r > 180 and g < 100 and b < 100:
                red_count += 1
        return red_count / total > 0.05
    except Exception:
        return False


def _detect_yellow_text(image: Image.Image) -> bool:
    """Crude yellow-text detection for training-hub shop alerts."""
    try:
        rgb = image.convert("RGB")
        pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        pixels = list(pixel_data)
        total = max(len(pixels), 1)
        yellow_count = 0
        for r, g, b in pixels:
            if r > 180 and g > 130 and b < 100:
                yellow_count += 1
        return yellow_count / total > 0.03
    except Exception:
        return False


def _or_none(text: str | None) -> str | None:
    t = (text or "").strip()
    return t if t else None


def _ocr_int_token_to_int(token: str) -> int:
    cleaned = token.translate(str.maketrans({"o": "0", "l": "1", "i": "1", "s": "5"}))
    return int(cleaned.replace(",", ""))
