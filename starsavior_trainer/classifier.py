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


# Small title/marker anchors that identify most screens on their own. OCR'ing
# only these first (then matching) avoids reading all ~54 anchor regions every
# frame — the dominant per-iteration cost (~5-6s). The full sweep runs only as a
# fallback when these don't give a confident match (rare / title-less screens).
_FAST_ANCHORS: tuple[str, ...] = (
    "route_select_anchor_title",
    "character_select_anchor_title",
    "blessing_setup_anchor_title",
    "blessing_choice_anchor_archive",
    "journey_start_anchor_title",
    "confirm_dialog_title",
    "event_fast_forward_title",
    "training_hub_anchor_title",
    "training_select_anchor_title",
    "training_select_card_power", "training_select_card_stamina",
    "training_select_card_guts", "training_select_card_wisdom", "training_select_card_speed",
    "event_choice_title",
    "relic_choice_title",
    "commission_select_anchor_title",
    "skill_select_title",
    "post_training_title",
    "dialogue_journey_title",
    # Story-intro cutscene has a top-right "SKIP" button (OCR-readable text, unlike
    # the journey dialogue's >> icon). Reading it in the fast pass lets the dialogue
    # signature catch the intro immediately instead of falling through to the full
    # 54-region sweep (which left it UNKNOWN at ~3.6s/frame).
    "dialogue_intro_skip_button",
    "reward_title",
    # Accidental in-game 菜单 popup: its top-left 菜单 title + centre 观测 menu
    # items are read in the fast pass so we recognise it and close it (click ✕)
    # instead of leaving it UNKNOWN and centre-clicking onto a dangerous menu item.
    "game_menu_anchor_title",
    "game_menu_observe_marker",
    # 列车月台 region-move: read its 地区移动 + 列车月台 anchors in the fast pass so it's
    # recognised as REGION_MOVE instead of falling through to a relic_choice misscore.
    "region_move_anchor_title",
    "region_move_station_title",
    # 赛前流程入口: 游戏主界面(左侧菜单竖排)与主界面菜单栏(图标网格行)。
    "main_screen_menu_column",
    "main_menu_panel_grid_text",
    # 通用筛选弹窗(覆盖在角色选择/刻印操作上, 必须先于底层画面的标题锚命中)。
    "filter_dialog_anchor_title",
    "filter_dialog_profession_row",
    # 好友卡流程三画面(标题与旅程起点共用, 靠各自特异锚区分)。
    "support_friend_list_anchor",
    "support_picker_borrow_anchor",
    "support_card_detail_anchor",
    # 达成目标列表黑底展示页(不识别会 unknown 死循环)。
    "goal_list_subtitle",
    # 跳过战斗二次确认弹窗(不识别会被蓝键误判成快转设置 → pause 死循环)。
    "skip_battle_confirm_text",
)


def classify_by_ocr(
    image: Image.Image,
    profile: RegionProfile,
    ocr: OcrEngine,
    min_confidence: float = 0.70,
) -> Observation:
    """Classify the current screen by reading OCR anchor regions.

    Two-pass for speed: first OCR only the small title/marker anchors
    (_FAST_ANCHORS) and try to match — most screens resolve here in a fraction of
    the OCR calls. Only if that yields no confident match do we OCR the full
    anchor set (covers ambiguous / title-less screens). The result is identical
    to the full sweep whenever the fast pass is confident.
    """

    fast_anchors = _read_anchor_regions(image, profile, ocr, names=_FAST_ANCHORS)
    best_screen, best_confidence = _match_screen(fast_anchors)
    if best_confidence >= min_confidence:
        return Observation(screen=best_screen, confidence=best_confidence)

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
            if screen == Screen.CONFIRM_DIALOG and not _has_confirm_dialog_panel(image, profile):
                continue
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


def _has_confirm_dialog_panel(image: Image.Image, profile: RegionProfile) -> bool:
    rect = profile.regions.get("confirm_dialog_panel")
    if rect is None:
        return False
    try:
        panel = crop_region(image, rect).convert("RGB")
        pixel_data = panel.get_flattened_data() if hasattr(panel, "get_flattened_data") else panel.getdata()
        pixels = list(pixel_data)
    except Exception as e:
        logger.debug(f"[_has_confirm_dialog_panel] panel detect failed: {e}")
        return False
    if not pixels:
        return False
    total = len(pixels)
    bright_ratio = sum(1 for red, green, blue in pixels if red + green + blue >= 630) / total
    mean_value = sum((red + green + blue) / 3 for red, green, blue in pixels) / total
    return bright_ratio >= 0.75 and mean_value >= 200.0


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

    # Journey DIALOGUE shares the "旅程事件" title with EVENT_CHOICE. In the fast
    # anchor pass the option rows aren't read, so a dialogue scores as event_choice
    # off the title alone — then the policy tries to pick an option, finds none, and
    # pauses (the "skip never happens / stuck on cutscene" symptom). If there are no
    # real option rows, it's a skippable dialogue. This OCR cost is paid ONLY when a
    # frame already looks like event_choice, not on every frame.
    if ocr_result.screen == Screen.EVENT_CHOICE and not _has_real_event_options(image, profile, ocr):
        return Observation(screen=Screen.DIALOGUE, confidence=max(ocr_result.confidence, 0.90))
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
            resolved = visual_screen if visual_screen is not None else ocr_result.screen
            # character_select & journey_start share the "旅程起点" title; tell them
            # apart by the bottom button ("选择" vs "旅程起点"). journey_start has no
            # character list, so misreading it as character_select stalls the
            # character-scroll loop forever. (blessing_setup is split off by visual.)
            if resolved == Screen.CHARACTER_SELECT and _looks_like_journey_start(image, profile, ocr):
                return Observation(screen=Screen.JOURNEY_START, confidence=max(ocr_result.confidence, 0.90))
            return Observation(screen=resolved, confidence=max(ocr_result.confidence, 0.90))
        return ocr_result

    blue_result = classify_by_blue_button(image, profile, blue_min_confidence)
    if blue_result.screen != Screen.UNKNOWN:
        return blue_result

    # Fallback — OCR-based anchor text matching.
    return ocr_result


def _has_real_event_options(image: Image.Image, profile: RegionProfile, ocr: OcrEngine) -> bool:
    """True if the screen has actual selectable event-choice option rows.

    Distinguishes a real EVENT_CHOICE from a journey DIALOGUE: both carry the
    "旅程事件" title, but only event_choice has option rows with text. Options are
    bottom-aligned on this UI, so option_3/4 are filled on every real event while
    option_1 is almost always empty — we scan options 2-4 (skipping the dead
    option_1 read) and accept any with real text. Fewer reads = faster recognition,
    which matters because this runs on every dialogue frame too."""
    for index in range(2, 5):
        rect = profile.regions.get(f"event_choice_option_{index}")
        if rect is None:
            continue
        try:
            text = ocr.read_text(crop_region(image, rect)).text.strip()
        except Exception as e:
            logger.debug(f"[_has_real_event_options] OCR failed on option {index}: {e}")
            continue
        if len(text) >= 2:
            return True
    return False


def _looks_like_journey_start(image: Image.Image, profile: RegionProfile, ocr: OcrEngine) -> bool:
    """Distinguish journey_start from character_select (they share the 旅程起点
    title + a bottom-right blue button). character_select's button reads 选择;
    journey_start's reads 旅程起点 (with 自动旅程 beside it). OCR that button."""
    rect = profile.regions.get("journey_start_button")
    if rect is None:
        return False
    text = ocr.read_text(crop_region(image, rect)).text
    if "选择" in text:
        return False
    return ("旅程" in text) or ("起点" in text) or ("自动" in text)


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
    Screen.MAIN_SCREEN: ["main_screen_menu_column"],
    Screen.MAIN_MENU_PANEL: ["main_menu_panel_grid_text"],
    Screen.FILTER_DIALOG: ["filter_dialog_anchor_title", "filter_dialog_profession_row"],
    Screen.SUPPORT_PICKER: ["support_picker_borrow_anchor"],
    Screen.SUPPORT_FRIEND_LIST: ["support_friend_list_anchor"],
    Screen.SUPPORT_CARD_DETAIL: ["support_card_detail_anchor"],
    Screen.GOAL_LIST: ["goal_list_subtitle"],
    Screen.SKIP_BATTLE_CONFIRM: ["skip_battle_confirm_text"],
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
    Screen.REWARD: ["reward_title"],
    Screen.COMMISSION_SELECT: [
        "commission_select_anchor_title",
        "commission_select_option_1_name",
        "commission_select_option_2_name",
        "commission_select_option_3_name",
        "commission_select_accept_button",
    ],
    Screen.SHOP: [
        "shop_refresh_button",
        "shop_buy_button",
        "shop_detail_effect",
        "shop_item_1_name",
        "shop_item_2_name",
        "shop_item_3_name",
        "shop_item_1_price",
        "shop_item_2_price",
        "shop_item_3_price",
    ],
    Screen.BATTLE: [
        "battle_skip_button",
        "battle_title",
        "battle_entry_button",
        "battle_accept_button",
        "battle_skip_battle_button",
        "battle_confirm_title",
    ],
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
    Screen.REWARD: ("\u83b7\u5f97\u5956\u52b1",),
    Screen.COMMISSION_SELECT: ("\u59d4\u6258",),
    Screen.SHOP: ("\u8d2d\u4e70",),
    Screen.BATTLE: ("\u8df3\u8fc7\u6218\u6597", "\u8bc4\u9274\u6218", "\u6218\u6597", "\u63a5\u53d7"),
    Screen.SKILL_SELECT: ("\u6f5c\u8d28", "\u6280\u80fd", "\u5b66\u4e60"),
    Screen.POST_TRAINING: ("\u63d0\u5347", "\u4e8b\u4ef6", "+"),
    Screen.REGION_MOVE: ("\u79fb\u52a8",),
}


def _read_anchor_regions(
    image: Image.Image,
    profile: RegionProfile,
    ocr: OcrEngine,
    names: tuple[str, ...] | None = None,
) -> dict[str, str]:
    anchors: dict[str, str] = {}
    if names is None:
        all_anchor_names: set[str] = set()
        for region_names in ANCHOR_REGIONS_BY_SCREEN.values():
            all_anchor_names.update(region_names)
        names = tuple(all_anchor_names)

    for name in names:
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
    # Ordered signature checks now dispatch through the screen registry. The
    # ANCHOR_HANDLERS list is sorted by priority to reproduce the exact original
    # order (initial -> post_training -> ... -> training_select). Imported lazily
    # to avoid an import cycle (screens/__init__ imports this module).
    from starsavior_trainer.screens import ANCHOR_HANDLERS

    for handler in ANCHOR_HANDLERS:
        matched, confidence = handler.has_anchor(anchors)
        if matched:
            return handler.screen, confidence

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
    # Journey Trading (交易) sits on the D-DAY background, so battle_title reads
    # 参加评鉴战 and fallback scoring would otherwise call it BATTLE — the shop needs
    # a signature to pre-empt that. The unique, ALWAYS-present marker is the top-right
    # 「刷新」(refresh) button (the 1级 D-DAY hub does NOT have it). The bottom 「购买」
    # button only appears once an item is selected — so relying on 购买 alone made the
    # screen go unknown whenever nothing was selected (just entered / a SOLD OUT item).
    # Accept EITHER, corroborated by any shop content (item name/price or the selected
    # item's effect detail) so a stray OCR elsewhere can't false-trigger.
    refresh_text = anchors.get("shop_refresh_button", "")
    buy_text = anchors.get("shop_buy_button", "")
    if not (contains_any_text(refresh_text, ("刷新",)) or contains_any_text(buy_text, ("购买", "购"))):
        return False
    detail = anchors.get("shop_detail_effect", "")
    names = " ".join(anchors.get(f"shop_item_{i}_name", "") for i in range(1, 6))
    prices = " ".join(anchors.get(f"shop_item_{i}_price", "") for i in range(1, 6))
    return bool(detail.strip() or names.strip() or prices.strip())


def _has_battle_signature(anchors: dict[str, str]) -> bool:
    # 基础评鉴战 entry confirm: a centred dialog (battle_title/skip_button live in the
    # top corners and read empty here), so classify_by_ocr would be UNKNOWN and the
    # blue-button fallback misreads the 跳过战斗 blue button as event_fast_forward.
    # The 跳过战斗 button text + 评鉴战 dialog title uniquely identify it as BATTLE.
    skip = anchors.get("battle_skip_battle_button", "")
    title = anchors.get("battle_confirm_title", "")
    # 评鉴战 与 委托 的战斗确认界面同布局(都有左下「跳过战斗」蓝键 + 中上标题)。标题
    # 是「基础评鉴战」或「XX讨伐委托」——两者都认, 否则委托确认会被误判 event_fast_forward。
    return contains_any_text(skip, ("跳过战斗", "跳过")) and contains_any_text(
        title, ("评鉴战", "鉴战", "委托")
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


def _has_reward_signature(anchors: dict[str, str]) -> bool:
    # "获得奖励" reward popup. Its title sits centre-top (reward_title), a region
    # that is empty on the journey-origin screens — so this fires only on the
    # real reward popup and pre-empts the weak character_select fallback (which
    # otherwise mis-scores this screen and stalls the character-scroll loop).
    title = anchors.get("reward_title", "")
    return contains_any_text(title, ("获得奖励", "获得", "奖励"))


def _has_region_move_signature(anchors: dict[str, str]) -> bool:
    # 列车月台 region-move screen: identified by its 地区移动 (top-left) + 列车月台
    # (right) titles together. Both required so a stray 月台/地区 elsewhere can't
    # false-trigger. Pre-empts the relic_choice fallback that otherwise mis-scored
    # this screen and left the bot centre-clicking onto the character art forever.
    anchor = anchors.get("region_move_anchor_title", "")
    station = anchors.get("region_move_station_title", "")
    return contains_any_text(anchor, ("地区移动", "区移动")) and contains_any_text(
        station, ("列车月台", "车月台", "月台")
    )


def _has_main_screen_signature(anchors: dict[str, str]) -> bool:
    # 游戏主界面: 左侧竖排菜单(战斗/管理/总部/公会/商店/观测)。要求 ≥2 个词命中
    # 才认, 单个词(如 商店)会在 SHOP 等画面出现, 两个以上的组合只有主界面有。
    column = anchors.get("main_screen_menu_column", "")
    if not column:
        return False
    words = ("战斗", "管理", "总部", "公会", "商店", "观测")
    return sum(1 for word in words if word in column) >= 2


def _has_main_menu_panel_signature(anchors: dict[str, str]) -> bool:
    # 主界面菜单栏面板: 必须同时有「旅程」和任一商店/故事/作战类词。区别于局内误触
    # 弹窗 GAME_MENU(那个是 菜单+观测 组合, 没有这排图标文字)。
    # 词表含新旧版本 UI 文案: 实机 2026-06 是 付费商店/主线故事/作战/旅程,
    # docx 旧截图是 付费商店/主线商店/作战/旅程。
    grid = anchors.get("main_menu_panel_grid_text", "")
    if "旅程" not in grid:
        return False
    return any(word in grid for word in ("付费商店", "主线商店", "主线故事", "作战", "酒馆", "培养"))


def _has_filter_dialog_signature(anchors: dict[str, str]) -> bool:
    # 通用「筛选」弹窗(角色选择的职业筛选 / 刻印操作的属性筛选, 同一 UI 组件):
    # 左上「筛选」标题 + 职业行任一职业词。两者都要 —— 角色列表本身也会 OCR 出
    # 职业词, 单靠职业词会把普通角色选择误判成筛选弹窗。
    title = anchors.get("filter_dialog_anchor_title", "")
    row = anchors.get("filter_dialog_profession_row", "")
    if "筛选" not in title:
        return False
    return any(word in row for word in ("坦克", "突击者", "游侠", "术师", "刺客", "辅助"))


def _has_skip_battle_confirm_signature(anchors: dict[str, str]) -> bool:
    # 「跳过战斗」二次确认弹窗: 中部问句(确定要跳过评鉴战战斗吗/跳过故事时…)。
    # 必须含「跳过」+(评鉴战/鉴战/战斗吗/故事)组合, 先于蓝键 fallback 命中,
    # 否则弹窗内的跳过战斗蓝键会压在快转设置确认键区域上被误判(实跑教训)。
    text = anchors.get("skip_battle_confirm_text", "")
    if "跳过" not in text:
        return False
    return any(word in text for word in ("评鉴战", "鉴战", "战斗吗", "故事"))


def _has_goal_list_signature(anchors: dict[str, str]) -> bool:
    # 「达成目标列表」黑底展示页: 画面中部副标题。黑屏其他锚全空, 这一条
    # 读到就足够特异。实机 OCR 把「目」读成「自」(达成自标列表 0.92),
    # 所以不用整词, 用「达成+列表」两个稳片段组合(布谷鸟时钟别名同款经验)。
    text = anchors.get("goal_list_subtitle", "")
    if "达成" in text and "列表" in text:
        return True
    return contains_any_text(text, ("目标列表", "自标列表"))


def _has_support_friend_list_signature(anchors: dict[str, str]) -> bool:
    # 好友支援卡墙: 顶部「可借用次数: N/N」。必须含「次数」, 用于和支援卡选择
    # 界面(只有「可借用」标签)区分; 有序检查时本签名排在 SUPPORT_PICKER 之前。
    text = anchors.get("support_friend_list_anchor", "")
    return "次数" in text and "可借用" in text


def _has_support_picker_signature(anchors: dict[str, str]) -> bool:
    # 支援卡选择界面: 左上「可借用」标签(没有这三个字 = 不能接好友卡, decide 会
    # 点返回退出)。锚区域只框标签处, 读到「可借用」即认; 「次数」由上面的好友卡墙
    # 签名先行截胡。
    text = anchors.get("support_picker_borrow_anchor", "")
    return "可借用" in text and "次数" not in text


def _has_support_card_detail_signature(anchors: dict[str, str]) -> bool:
    # 支援卡详情: 右侧标签列 旅程效果/专属效果。两词至少命中一个 + 必须有「效果」,
    # 避免单字噪声; 该画面只在好友卡流程出现, 风险低。
    text = anchors.get("support_card_detail_anchor", "")
    return any(word in text for word in ("旅程效果", "专属效果", "训练效果"))


def _has_game_menu_signature(anchors: dict[str, str]) -> bool:
    # The accidental in-game 菜单 popup (指南/选项/编制信息/观测信息/重新观测/储存后
    # 前往大厅 + ✕). Identify it by its top-left 菜单 title AND the 观测 menu items in
    # the centre row. Both are required: the bare word 菜单 can appear elsewhere, but
    # 菜单-title + 观测-row together are unique to this popup, so we never
    # false-positive a normal screen into "close the menu".
    title = anchors.get("game_menu_anchor_title", "")
    observe = anchors.get("game_menu_observe_marker", "")
    return contains_any_text(title, ("菜单", "菜車", "茶单")) and contains_any_text(
        observe, ("观测", "重新观测", "观测结束", "观测信息")
    )


def _has_training_select_signature(anchors: dict[str, str]) -> bool:
    # Count how many card slots read a training name. A real training screen has all
    # five (\u529b\u91cf/\u4f53\u529b/\u97e7\u6027/\u96c6\u4e2d/\u4fdd\u62a4\u8bad\u7ec3); the D-DAY trading shop merely SELLS a
    # "\u4fdd\u62a4\u8bad\u7ec3\u7684\u79d8\u7b08" item, so at most ONE card slot matches there. Require \u22652 so the
    # shop (and any stray single-card OCR) isn't mis-read as TRAINING_SELECT \u2014 which
    # made the training inspector loop forever clicking a non-existent training card.
    names = (
        "\u529b\u91cf\u8bad\u7ec3",
        "\u4f53\u529b\u8bad\u7ec3",
        "\u97e7\u6027\u8bad\u7ec3",
        "\u96c6\u4e2d\u8bad\u7ec3",
        "\u4fdd\u62a4\u8bad\u7ec3",
    )
    hits = sum(
        1
        for attr in ("power", "stamina", "guts", "wisdom", "speed")
        if contains_any_text(anchors.get(f"training_select_card_{attr}", ""), names)
    )
    return hits >= 2


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
