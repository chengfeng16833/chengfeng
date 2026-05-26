from __future__ import annotations

from pathlib import Path

from PIL import Image
from starsavior_trainer.image_regions import crop_region
from starsavior_trainer.logging_setup import get_logger
from starsavior_trainer.models import Observation, Screen
from starsavior_trainer.ocr import OcrEngine, OcrResult
from starsavior_trainer.regions import RegionProfile
from starsavior_trainer.screen_reader import contains_any_text, normalize_ocr_text
from starsavior_trainer.vision import BlueButtonDetector

logger = get_logger("classifier")


def classify_by_ocr(
    image: Image.Image,
    profile: RegionProfile,
    ocr: OcrEngine,
    min_confidence: float = 0.70,
) -> Observation:
    """Classify the current screen by reading OCR anchor regions.

    Each screen has one or more anchor regions that contain reliable text.
    The classifier reads these regions and returns the best match.
    """

    anchors = _read_anchor_regions(image, profile, ocr)
    if not anchors:
        return Observation(screen=Screen.UNKNOWN, confidence=0.0)

    best_screen, best_confidence = _match_screen(anchors)
    if best_confidence < min_confidence:
        return Observation(screen=Screen.UNKNOWN, confidence=best_confidence)
    return Observation(screen=best_screen, confidence=best_confidence)


# ---------------------------------------------------------------------------
# Blue-button-based classification (no OCR)
# ---------------------------------------------------------------------------

# Unique-position blue buttons that directly identify a screen.
UNIQUE_BLUE_BUTTONS: dict[str, Screen] = {
    "confirm_dialog_confirm_button": Screen.CONFIRM_DIALOG,
    "event_fast_forward_confirm_button": Screen.EVENT_FAST_FORWARD_SETTING,
    "relic_choice_confirm_button": Screen.RELIC_CHOICE,
    "battle_accept_button": Screen.BATTLE,
    "training_hub_action_training": Screen.TRAINING_HUB,
    "region_move_button": Screen.REGION_MOVE,
    "blessing_choice_confirm_button": Screen.BLESSING_CHOICE,
    "journey_start_button": Screen.JOURNEY_START,
}

# Bottom-right group: multiple screens share nearly identical blue button positions.
# We check the blue button first, then use secondary regions for disambiguation.
_BOTTOM_RIGHT_BUTTONS: list[tuple[str, Screen]] = [
    ("start_button", Screen.INITIAL),
    ("character_select_button", Screen.CHARACTER_SELECT),
    ("blessing_confirm_button", Screen.BLESSING_SETUP),
    ("training_select_confirm_button", Screen.TRAINING_SELECT),
]

# Secondary disambiguation regions (checked for visual content density).
# Higher content density → this screen is more likely the current one.
_SECONDARY_CHECK_REGIONS: dict[Screen, list[str]] = {
    Screen.TRAINING_SELECT: [
        "training_select_card_power",
        "training_select_card_stamina",
        "training_select_card_guts",
    ],
    Screen.CHARACTER_SELECT: [
        "character_option_1",
        "character_option_2",
        "character_option_3",
    ],
    Screen.BLESSING_SETUP: [
        "blessing_slot_1",
        "blessing_slot_2",
    ],
    # INITIAL has no secondary check — it's the fallback.
}


def classify_by_blue_button(
    image: Image.Image,
    profile: RegionProfile,
    min_confidence: float = 0.60,
) -> Observation:
    """Classify the current screen by detecting blue buttons at known positions.

    This is the primary classifier for color-based operation mode.
    It does not use OCR — only pixel color analysis via BlueButtonDetector.
    """
    detector = BlueButtonDetector()

    # Phase 1 — Unique blue buttons with distinctive positions.
    for region_name, screen in UNIQUE_BLUE_BUTTONS.items():
        rect = profile.regions.get(region_name)
        if rect is None:
            continue
        try:
            signal = detector.detect(crop_region(image, rect))
            if signal.name == "active_blue" and signal.confidence >= min_confidence:
                return Observation(screen=screen, confidence=signal.confidence)
        except Exception as e:
            logger.debug(f"[classify_by_blue_button] blue detect failed on {region_name}: {e}")
            continue

    # Phase 2 — Bottom-right overlapping group with secondary disambiguation.
    br_result = _classify_bottom_right_group(image, profile, detector, min_confidence)
    if br_result is not None:
        return br_result

    return Observation(screen=Screen.UNKNOWN, confidence=0.0)


def _classify_bottom_right_group(
    image: Image.Image,
    profile: RegionProfile,
    detector: BlueButtonDetector,
    min_confidence: float,
) -> Observation | None:
    """Disambiguate the bottom-right blue-button group using secondary region checks."""
    # First, verify that ANY bottom-right blue button is active.
    active_screens: list[Screen] = []
    for region_name, screen in _BOTTOM_RIGHT_BUTTONS:
        rect = profile.regions.get(region_name)
        if rect is None:
            continue
        try:
            signal = detector.detect(crop_region(image, rect))
            if signal.name == "active_blue":
                active_screens.append(screen)
        except Exception as e:
            logger.debug(f"[_classify_bottom_right_group] blue detect failed on {region_name}: {e}")
            continue

    if not active_screens:
        return None

    # Secondary disambiguation: check which screen's secondary regions have the highest content density.
    scores: dict[Screen, float] = {}
    for screen in active_screens:
        secondary_regions = _SECONDARY_CHECK_REGIONS.get(screen, [])
        if not secondary_regions:
            # INITIAL (no secondary regions) gets a baseline score.
            scores[screen] = 0.3
            continue
        densities = []
        for name in secondary_regions:
            rect = profile.regions.get(name)
            if rect is not None:
                densities.append(_region_content_density(crop_region(image, rect)))
        scores[screen] = max(densities) if densities else 0.3

    best_screen = max(scores, key=lambda s: scores[s])
    return Observation(screen=best_screen, confidence=min(scores[best_screen], 1.0))


def classify_hybrid(
    image: Image.Image,
    profile: RegionProfile,
    ocr: OcrEngine,
    blue_min_confidence: float = 0.60,
    ocr_min_confidence: float = 0.70,
) -> Observation:
    """Classify screen with OCR first, fallback to blue-button detection.

    OCR anchors are slower but safer when multiple screens share blue button
    positions. Blue detection remains a fallback for OCR-poor screens.
    """
    # Fast path — blue button color detection.
    ocr_result = classify_by_ocr(image, profile, ocr, ocr_min_confidence)
    # Blessing choice shares the "旅程起点" anchor text with the journey-origin
    # screens, so its visual signature only disambiguates that group. Applying it
    # unconditionally misfires on any screen with a bottom-right blue button plus
    # upper-left content (e.g. INITIAL's "开始" button), so gate it on ambiguity.
    _BLESSING_AMBIGUOUS = (
        Screen.UNKNOWN,
        Screen.CHARACTER_SELECT,
        Screen.BLESSING_SETUP,
        Screen.JOURNEY_START,
        Screen.BLESSING_CHOICE,
    )
    if ocr_result.screen in _BLESSING_AMBIGUOUS and _has_blessing_choice_visual_signature(image, profile):
        return Observation(screen=Screen.BLESSING_CHOICE, confidence=max(ocr_result.confidence, 0.95))
    if ocr_result.screen != Screen.UNKNOWN:
        if ocr_result.screen in (Screen.CHARACTER_SELECT, Screen.BLESSING_SETUP):
            visual_screen = classify_journey_origin_by_visual(image, profile)
            if visual_screen is not None:
                return Observation(screen=visual_screen, confidence=max(ocr_result.confidence, 0.90))
        return ocr_result

    blue_result = classify_by_blue_button(image, profile, blue_min_confidence)
    if blue_result.screen != Screen.UNKNOWN:
        return blue_result

    # Fallback — OCR-based anchor text matching.
    return ocr_result


def classify_by_filename(path: str | Path) -> Observation:
    """Temporary classifier for offline screenshots.

    Until OCR and templates are connected, screenshots can be named with a
    screen state, for example `training_select_001.png`.
    """

    name = Path(path).stem.lower()
    if "route_select" in name or "journey_select" in name:
        return Observation(screen=Screen.INITIAL, confidence=0.80, source=str(path))
    if "character_select" in name or "select_character" in name or "runner_select" in name:
        return Observation(screen=Screen.CHARACTER_SELECT, confidence=0.80, source=str(path))
    if "blessing_setup" in name or "blessing_equip" in name:
        return Observation(screen=Screen.BLESSING_SETUP, confidence=0.80, source=str(path))
    if "blessing_choice" in name or "select_blessing" in name:
        return Observation(screen=Screen.BLESSING_CHOICE, confidence=0.80, source=str(path))
    if "journey_start" in name or "journey_origin" in name or "arcana" in name:
        return Observation(screen=Screen.JOURNEY_START, confidence=0.80, source=str(path))
    if "confirm_dialog" in name or "entry_confirm" in name:
        return Observation(screen=Screen.CONFIRM_DIALOG, confidence=0.80, source=str(path))
    if "event_fast_forward" in name or "fast_forward_setting" in name:
        return Observation(screen=Screen.EVENT_FAST_FORWARD_SETTING, confidence=0.80, source=str(path))
    if "dialogue_intro" in name or "story_skip" in name or "journey_dialogue" in name:
        return Observation(screen=Screen.DIALOGUE, confidence=0.80, source=str(path))
    if "training_hub" in name or "training_main" in name or "action_hub" in name:
        return Observation(screen=Screen.TRAINING_HUB, confidence=0.80, source=str(path))
    if "training_select" in name and "training_hub" not in name:
        return Observation(screen=Screen.TRAINING_SELECT, confidence=0.80, source=str(path))
    if "training_direction" in name:
        return Observation(screen=Screen.EVENT_CHOICE, confidence=0.80, source=str(path))
    if "post_training" in name:
        return Observation(screen=Screen.POST_TRAINING, confidence=0.80, source=str(path))
    if "battle" in name or "\u8bc4\u9274\u6218" in name or "skip_battle" in name:
        return Observation(screen=Screen.BATTLE, confidence=0.80, source=str(path))
    if "skill" in name or "\u6280\u80fd" in name or "\u6f5c\u8d28" in name:
        return Observation(screen=Screen.SKILL_SELECT, confidence=0.80, source=str(path))
    for screen in Screen:
        if screen != Screen.UNKNOWN and screen.value in name:
            return Observation(screen=screen, confidence=0.80, source=str(path))
    return Observation(screen=Screen.UNKNOWN, confidence=0.0, source=str(path))


# ---- OCR-based anchor matching ----


ANCHOR_REGIONS_BY_SCREEN: dict[Screen, list[str]] = {
    Screen.INITIAL: ["route_select_anchor_title", "route_select_route_title", "start_button"],
    Screen.CHARACTER_SELECT: ["character_select_anchor_title"],
    Screen.BLESSING_SETUP: ["blessing_setup_anchor_title"],
    Screen.BLESSING_CHOICE: ["blessing_choice_anchor_archive"],
    Screen.JOURNEY_START: ["journey_start_anchor_title"],
    Screen.CONFIRM_DIALOG: ["confirm_dialog_title"],
    Screen.EVENT_FAST_FORWARD_SETTING: ["event_fast_forward_title"],
    Screen.DIALOGUE: [
        "dialogue_intro_skip_button",
        "dialogue_journey_title",
        "dialogue_journey_event_label",
        "dialogue_journey_text_area",
    ],
    Screen.TRAINING_HUB: [
        "training_hub_anchor_title",
        "training_hub_distance",
        "training_hub_action_training",
        "training_hub_action_commission",
        "training_hub_action_shop",
        "training_hub_action_rest",
        "training_hub_shop_alert",
        "training_hub_nav_potential",
    ],
    Screen.TRAINING_SELECT: [
        "training_select_anchor_title",
        "training_select_card_power",
        "training_select_card_stamina",
        "training_select_card_guts",
        "training_select_card_wisdom",
        "training_select_card_speed",
    ],
    Screen.REST_SUBMENU: ["rest_submenu_option_1", "rest_submenu_option_2", "rest_submenu_option_3"],
    Screen.EVENT_CHOICE: [
        "event_choice_title",
        "event_choice_option_1",
        "event_choice_option_2",
        "event_choice_option_3",
        "event_choice_option_4",
    ],
    Screen.RELIC_CHOICE: ["relic_choice_title"],
    Screen.COMMISSION_SELECT: [
        "commission_select_anchor_title",
        "commission_select_option_1_name",
        "commission_select_option_2_name",
        "commission_select_option_3_name",
        "commission_select_accept_button",
    ],
    Screen.SHOP: [
        "shop_item_1",
        "shop_item_1_name",
        "shop_item_2_name",
        "shop_item_1_price",
        "shop_item_2_price",
    ],
    Screen.BATTLE: ["battle_skip_button", "battle_title", "battle_entry_button", "battle_accept_button"],
    Screen.SKILL_SELECT: ["skill_select_title"],
    Screen.POST_TRAINING: [
        "post_training_result_text",
        "post_training_title",
        "post_training_success_text",
        "post_training_event_title",
    ],
    Screen.REGION_MOVE: ["region_move_button"],
}

ANCHOR_TEXT_BY_SCREEN: dict[Screen, tuple[str, ...]] = {
    Screen.INITIAL: ("\u9009\u62e9\u65c5\u7a0b", "\u661f\u5149\u5f15\u5bfc\u8005", "starsavior", "\u5f00\u59cb"),
    Screen.CHARACTER_SELECT: ("\u65c5\u7a0b\u8d77\u70b9",),
    Screen.BLESSING_SETUP: ("\u65c5\u7a0b\u8d77\u70b9",),
    Screen.BLESSING_CHOICE: ("\u661f\u8fb0\u6863\u6848",),
    Screen.JOURNEY_START: ("\u65c5\u7a0b\u8d77\u70b9",),
    Screen.CONFIRM_DIALOG: ("\u5165\u573a\u786e\u8ba4",),
    Screen.EVENT_FAST_FORWARD_SETTING: ("\u4e8b\u4ef6\u5feb\u8f6c\u8bbe\u5b9a",),
    Screen.DIALOGUE: ("skip", "\u8df3\u8fc7", "\u65c5\u7a0b\u4e8b\u4ef6"),
    Screen.TRAINING_HUB: ("\u8ddd\u79bb\u76ee\u6807", "\u8bad\u7ec3", "\u59d4\u6258", "\u4ea4\u6613", "\u4f11\u606f", "\u6f5c\u8d28", "\u5546\u54c1"),
    Screen.TRAINING_SELECT: ("\u529b\u91cf\u8bad\u7ec3", "\u4f53\u529b\u8bad\u7ec3", "\u97e7\u6027\u8bad\u7ec3", "\u96c6\u4e2d\u8bad\u7ec3"),
    Screen.REST_SUBMENU: ("\u9732\u5bbf", "\u51a5\u60f3"),
    Screen.EVENT_CHOICE: ("\u65c5\u7a0b\u4e8b\u4ef6", "\u4e8b\u4ef6"),
    Screen.RELIC_CHOICE: ("\u9009\u62e9\u5956\u52b1",),
    Screen.COMMISSION_SELECT: ("\u59d4\u6258",),
    Screen.SHOP: ("\u8d2d\u4e70",),
    Screen.BATTLE: ("\u8df3\u8fc7\u6218\u6597", "\u8bc4\u9274\u6218", "\u5e73\u9274\u6218", "\u6218\u6597", "\u63a5\u53d7"),
    Screen.SKILL_SELECT: ("\u6f5c\u8d28", "\u6280\u80fd", "\u5b66\u4e60"),
    Screen.POST_TRAINING: ("\u63d0\u5347", "\u4e8b\u4ef6", "+"),
    Screen.REGION_MOVE: ("\u79fb\u52a8",),
}


def _read_anchor_regions(image: Image.Image, profile: RegionProfile, ocr: OcrEngine) -> dict[str, str]:
    anchors: dict[str, str] = {}
    all_anchor_names: set[str] = set()
    for names in ANCHOR_REGIONS_BY_SCREEN.values():
        all_anchor_names.update(names)

    for name in all_anchor_names:
        rect = profile.regions.get(name)
        if rect is None:
            continue
        try:
            result = ocr.read_text(crop_region(image, rect))
            if result.confidence > 0.5:
                anchors[name] = result.text
        except Exception as e:
            logger.debug(f"[_read_anchor_texts] OCR failed on {name}: {e}")
            continue

    return anchors


def _match_screen(anchors: dict[str, str]) -> tuple[Screen, float]:
    if _has_initial_signature(anchors):
        return Screen.INITIAL, 1.0
    if _has_post_training_signature(anchors):
        return Screen.POST_TRAINING, 1.0
    if _has_event_choice_signature(anchors):
        return Screen.EVENT_CHOICE, 1.0
    if _has_dialogue_signature(anchors):
        return Screen.DIALOGUE, 1.0
    if _has_rest_submenu_signature(anchors):
        return Screen.REST_SUBMENU, 1.0
    if _has_commission_select_signature(anchors):
        return Screen.COMMISSION_SELECT, 1.0
    if _has_shop_signature(anchors):
        return Screen.SHOP, 1.0
    if _has_training_hub_shop_signature(anchors):
        return Screen.TRAINING_HUB, 1.0
    if _has_training_select_signature(anchors):
        return Screen.TRAINING_SELECT, 0.90

    best_screen = Screen.UNKNOWN
    best_score = 0.0

    for screen, region_names in ANCHOR_REGIONS_BY_SCREEN.items():
        expected_texts = ANCHOR_TEXT_BY_SCREEN.get(screen, ())
        if not expected_texts:
            continue

        match_count = 0
        seen_regions = 0
        for name in region_names:
            text = anchors.get(name, "")
            if text.strip():
                seen_regions += 1
            if text.strip() and contains_any_text(text, expected_texts):
                match_count += 1

        if seen_regions > 0 and match_count > 0:
            score = match_count / seen_regions
            if score > best_score:
                best_score = score
                best_screen = screen

    return best_screen, min(best_score, 1.0)


def _has_initial_signature(anchors: dict[str, str]) -> bool:
    start_text = anchors.get("start_button", "")
    route_text = " ".join(
        anchors.get(name, "")
        for name in (
            "route_select_anchor_title",
            "route_select_route_title",
        )
    )
    return contains_any_text(start_text, ("\u5f00\u59cb",)) and contains_any_text(
        route_text,
        ("\u9009\u62e9\u65c5\u7a0b", "\u661f\u5149\u5f15\u5bfc\u8005", "starsavior"),
    )


def _has_post_training_signature(anchors: dict[str, str]) -> bool:
    post_text = " ".join(
        anchors.get(name, "")
        for name in (
            "post_training_result_text",
            "post_training_title",
            "post_training_success_text",
        )
    )
    return contains_any_text(post_text, ("\u8bad\u7ec3\u6210\u529f", "\u529b\u91cf\u8bad\u7ec3", "\u4f53\u529b\u8bad\u7ec3", "\u63d0\u5347"))


def _has_event_choice_signature(anchors: dict[str, str]) -> bool:
    option_text = " ".join(
        anchors.get(f"event_choice_option_{index}", "")
        for index in range(1, 5)
    )
    return bool(option_text.strip()) and contains_any_text(
        anchors.get("event_choice_title", ""),
        ("\u65c5\u7a0b\u4e8b\u4ef6", "\u4e8b\u4ef6"),
    )


def _has_dialogue_signature(anchors: dict[str, str]) -> bool:
    event_label = anchors.get("dialogue_journey_event_label", "") + anchors.get("dialogue_journey_title", "")
    bottom_text = anchors.get("dialogue_journey_text_area", "")
    if bottom_text.strip() and contains_any_text(event_label, ("\u4e8b\u4ef6",)):
        return True

    dialogue_text = " ".join(
        anchors.get(name, "")
        for name in (
            "dialogue_intro_skip_button",
            "dialogue_journey_event_label",
            "dialogue_journey_text_area",
        )
    )
    return contains_any_text(
        dialogue_text,
        ("\u83b7\u5f97", "\u661f\u4e4b\u795d\u798f", "\u8df3\u8fc7", "skip"),
    )


def _has_commission_select_signature(anchors: dict[str, str]) -> bool:
    title = anchors.get("commission_select_anchor_title", "")
    names = " ".join(anchors.get(f"commission_select_option_{i}_name", "") for i in range(1, 6))
    accept = anchors.get("commission_select_accept_button", "")
    # The title bar reads the journey name, so "委托" lives in the per-commission
    # names. But the training hub also has a 委托 button, so require the unique
    # 接受 (accept) button to disambiguate from the hub.
    has_commission_text = contains_any_text(names, ("委托", "commission")) or contains_any_text(
        title, ("委托", "commission")
    )
    # OCR sometimes misreads 受 as 文; match the leading 接 to stay robust.
    has_accept = contains_any_text(accept, ("接受", "接", "accept"))
    return has_commission_text and has_accept


def _has_shop_signature(anchors: dict[str, str]) -> bool:
    # shop_item_1 covers the full first row including the "购买" button on the right.
    item1_text = anchors.get("shop_item_1", "")
    names = " ".join(anchors.get(f"shop_item_{i}_name", "") for i in range(1, 6))
    prices = " ".join(anchors.get(f"shop_item_{i}_price", "") for i in range(1, 6))
    return (
        contains_any_text(item1_text, ("购买", "shop", "商品", "交易"))
        and bool(names.strip())
        and bool(prices.strip())
    )


def _has_training_hub_shop_signature(anchors: dict[str, str]) -> bool:
    shop_text = " ".join(
        anchors.get(name, "")
        for name in (
            "training_hub_action_shop",
            "training_hub_shop_alert",
            "training_hub_nav_potential",
        )
    )
    return contains_any_text(shop_text, ("\u4ea4\u6613", "\u5546\u54c1", "\u5230\u8d27")) and contains_any_text(
        shop_text,
        ("\u6f5c\u8d28", "\u5546\u54c1", "\u5230\u8d27"),
    )


def _has_rest_submenu_signature(anchors: dict[str, str]) -> bool:
    rest_text = " ".join(
        anchors.get(name, "")
        for name in (
            "rest_submenu_option_1",
            "rest_submenu_option_2",
            "rest_submenu_option_3",
        )
    )
    return contains_any_text(rest_text, ("\u9732\u5bbf", "\u4f4f\u5904", "\u51a5\u60f3\u5ba4"))


def _has_training_select_signature(anchors: dict[str, str]) -> bool:
    card_text = " ".join(
        anchors.get(f"training_select_card_{attr}", "")
        for attr in ("power", "stamina", "guts", "wisdom", "speed")
    )
    return contains_any_text(
        card_text,
        (
            "\u529b\u91cf\u8bad\u7ec3",
            "\u4f53\u529b\u8bad\u7ec3",
            "\u97e7\u6027\u8bad\u7ec3",
            "\u96c6\u4e2d\u8bad\u7ec3",
            "\u4fdd\u62a4\u8bad\u7ec3",
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _region_content_density(image: Image.Image) -> float:
    """Estimate visual content density via pixel variance.

    A region with UI elements (text, icons, cards) produces higher variance
    than a uniform background. Returns 0.0 (uniform) to ~1.0 (dense).
    """
    try:
        gray = image.convert("L")
        pixel_data = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
        pixels = list(pixel_data)
        total = len(pixels)
        if total < 2:
            return 0.0
        mean = sum(pixels) / total
        variance = sum((p - mean) ** 2 for p in pixels) / total
        return min(variance / 4000.0, 1.0)
    except Exception as e:
        logger.debug(f"[_region_content_density] failed: {e}")
        return 0.0


def _has_blessing_choice_visual_signature(image: Image.Image, profile: RegionProfile) -> bool:
    confirm = profile.regions.get("blessing_choice_confirm_button")
    archive = profile.regions.get("blessing_choice_anchor_archive")
    if confirm is None or archive is None:
        return False
    try:
        confirm_signal = BlueButtonDetector().detect(crop_region(image, confirm))
        archive_density = _region_content_density(crop_region(image, archive))
        return confirm_signal.name == "active_blue" and confirm_signal.coverage >= 0.40 and archive_density >= 0.40
    except Exception as e:
        logger.debug(f"[_has_blessing_choice_visual_signature] failed: {e}")
        return False


def classify_journey_origin_by_visual(image: Image.Image, profile: RegionProfile) -> Screen | None:
    """Separate character select from blessing setup when both OCR as journey origin."""
    character_score, blessing_score = journey_origin_visual_scores(image, profile)
    if character_score < 0.40 and blessing_score >= 0.18:
        return Screen.BLESSING_SETUP
    if blessing_score >= 0.45 and blessing_score > character_score + 0.18:
        return Screen.BLESSING_SETUP
    if character_score >= 0.75 and character_score >= blessing_score:
        return Screen.CHARACTER_SELECT
    return None


def journey_origin_visual_scores(image: Image.Image, profile: RegionProfile) -> tuple[float, float]:
    character_score = _average_region_density(image, profile, ("character_option_1", "character_option_2", "character_option_3"))
    blessing_score = _average_region_density(image, profile, ("blessing_slot_1", "blessing_slot_2"))
    return character_score, blessing_score


_classify_journey_origin_by_visual = classify_journey_origin_by_visual


def _average_region_density(image: Image.Image, profile: RegionProfile, names: tuple[str, ...]) -> float:
    densities: list[float] = []
    for name in names:
        rect = profile.regions.get(name)
        if rect is not None:
            densities.append(_region_content_density(crop_region(image, rect)))
    if not densities:
        return 0.0
    return sum(densities) / len(densities)


if __name__ == "__main__":
    # Quick smoke test
    print("classifier.py loaded OK")
    print(f"  {len(ANCHOR_REGIONS_BY_SCREEN)} screens with anchor regions defined")
    print(f"  {len(ANCHOR_TEXT_BY_SCREEN)} screens with anchor text defined")
    print(f"  {len(UNIQUE_BLUE_BUTTONS)} screens with unique blue button positions")
    # Smoke-test _region_content_density
    from PIL import Image as PILImage
    solid = PILImage.new("RGB", (100, 50), color=(128, 128, 128))
    print(f"  content density (solid gray): {_region_content_density(solid):.3f}")
