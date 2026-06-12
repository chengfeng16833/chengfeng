from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable
from typing import Iterable

from PIL import Image

from starsavior_trainer.image_regions import crop_region
from starsavior_trainer.logging_setup import get_logger
from starsavior_trainer.models import (
    BattleScene,
    BlessingChoice,
    BlessingOption,
    BlessingSetup,
    BlessingSlot,
    CharacterOption,
    CharacterSelect,
    FilterDialog,
    ConfirmDialog,
    CommissionChoice,
    CommissionOption,
    DialogueScene,
    EventFastForwardSetting,
    EventOption,
    JourneyStart,
    MainMenuPanel,
    MainScreen,
    Rect,
    RelicChoice,
    RelicOption,
    SupportCardDetail,
    SupportFriendCard,
    SupportFriendList,
    SupportPicker,
    RestSubmenu,
    ShopItem,
    ShopScene,
    SkillOption,
    TrainingChoice,
    TrainingHubStatus,
)
from starsavior_trainer.ocr import OcrEngine, OcrResult
from starsavior_trainer.regions import RegionProfile
from starsavior_trainer.vision import (
    BlueButtonDetector,
    RingColorDetector,
    bright_border_ratio as _bright_border_ratio,
    card_highlight_score as _card_highlight_score,
    detail_sub_blessing_slot_filled as _detail_sub_blessing_slot_filled,
    detect_red_text as _detect_red_text,
    detect_yellow_text as _detect_yellow_text,
    is_blessing_slot_filled as _is_blessing_slot_filled,
    is_blue_region as _is_blue_region,
)

logger = get_logger("screen_reader")

ATTRIBUTE_ALIASES = {
    "power": ("\u529b\u91cf", "power"),
    "stamina": ("\u4f53\u529b", "\u8010\u529b", "stamina", "hp"),
    "guts": ("\u97e7\u6027", "\u4fdd\u62a4", "guts", "protection"),
    "wisdom": ("\u4e13\u6ce8", "\u667a\u529b", "focus", "wisdom"),
    "speed": ("\u901f\u5ea6", "speed"),
}

RELIC_NAME_ALIASES = {
    "soft_toy_friend": ("\u8f6f\u7ef5\u7ef5\u7684\u73a9\u5076\u670b\u53cb", "\u73a9\u5076\u670b\u53cb"),
    # The cuckoo clock is the highlighted/enlarged card on the initial relic
    # screen, so its name OCRs garbled (e.g. "\u65f6\u5e03\u8c37\u9e1f\u65f6"). Match on the distinctive
    # "\u5e03\u8c37\u9e1f" (cuckoo) alone so it's still recognized \u2014 otherwise the fixed initial
    # pick fails to trigger and the bot picks a different relic by score.
    "annoying_cuckoo_clock": ("\u70e6\u4eba\u7684\u5e03\u8c37\u9e1f\u65f6\u949f", "\u5e03\u8c37\u9e1f\u65f6\u949f", "\u5e03\u8c37\u9e1f"),
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


def parse_rank_number(text: str) -> int | None:
    """Extract the level number from a 'RANK 21' / 'RANK17' / 'RANK 17 一级' label.

    parse_first_int refuses a digit glued to a letter (its ``(?<![a-z])`` guard),
    so 'RANK17' would lose the leading '1' and read as 7. Rank labels legitimately
    glue the number to 'RANK', so here we take the first OCR-digit run regardless
    of an adjacent letter.
    """
    normalized = normalize_ocr_text(text)
    match = re.search(r"[0-9olis][0-9olis,]*", normalized)
    if match is None:
        return None
    return _ocr_int_token_to_int(match.group(0))


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
        filter_button=profile.regions.get("character_select_filter_button"),
    )


def parse_character_select_bbox(
    image: Image.Image,
    profile: RegionProfile,
    ocr: OcrEngine,
) -> CharacterSelect | None:
    """Build the character-select payload by locating names via OCR bounding
    boxes instead of fixed row regions.

    The list scrolls by dragging and stops at arbitrary (half-row) offsets, so
    the fixed character_option_N regions read only the sliced gaps between rows.
    Here we OCR the whole list column once and use each detected block's box to
    drop a clickable target on the actual name, wherever it landed.
    """
    confirm_button = profile.regions.get("character_select_button")
    if confirm_button is None:
        return None

    # Selected character (left panel).
    sel_rect = profile.regions.get("character_selected_name")
    selected_name = None
    if sel_rect is not None:
        sel_text = ocr.read_text(crop_region(image, sel_rect))
        if sel_text.text and sel_text.confidence > 0.4:
            selected_name = extract_character_name(sel_text.text) or _or_none(sel_text.text)

    # List area = envelope of the 7 fixed option slots (covers the whole column).
    first = profile.regions.get("character_option_1")
    last = profile.regions.get("character_option_7")
    if first is None or last is None:
        return None
    lx, ly = first.x, first.y
    lw = first.width
    lh = (last.y + last.height) - first.y
    list_region = Rect(lx, ly, lw, lh)

    # Two passes over the OCR lines: collect name rows + their click targets, and
    # collect form-marker tokens (ANOTHER/COSMIC text under each row's class icon).
    lines = ocr.read_lines(crop_region(image, list_region))
    name_rows: list[tuple[str, int, Rect]] = []  # (name, y_top, target)
    variant_tokens: list[tuple[str, int]] = []  # (raw_text, y_top)
    for line in lines:
        x1, y1, x2, y2 = line.box
        name = extract_character_name(line.text)
        if name and len(name) >= 2:  # len<2 drops single-char noise (e.g. '双' from a level badge)
            cx = lx + (x1 + x2) // 2
            cy = ly + (y1 + y2) // 2
            target = Rect(max(cx - 90, 0), max(cy - 28, 0), 180, 56)
            name_rows.append((name, y1, target))
        elif _normalize_variant(line.text):
            variant_tokens.append((line.text, y1))

    # Associate each form-marker to the name row directly above it.
    variants = _match_character_variants([(n, y) for n, y, _t in name_rows], variant_tokens)

    # Dedup by (name, variant): same-named characters now have multiple forms
    # (普通 / ANOTHER / COSMIC) — keeping only `name` collapsed two 卡蜜 into one.
    options: list[CharacterOption] = []
    seen: set[tuple[str, str]] = set()
    for (name, _y, target), variant in zip(name_rows, variants):
        key = (name, variant)
        if key in seen:
            continue
        seen.add(key)
        options.append(
            CharacterOption(
                name=name, rank=None, stars=None, specialty=None,
                selected=(name == selected_name and not variant), target=target, variant=variant,
            )
        )

    # Always include the left-panel selected character as a fallback target.
    selected_target = sel_rect or confirm_button
    selected_option = CharacterOption(
        name=selected_name or "selected_character", rank=None, stars=None,
        specialty=None, selected=True, target=selected_target,
    )
    if not any(opt.name == selected_option.name for opt in options):
        options.insert(0, selected_option)

    # Dragging can always move the list further, so as long as we recognised at
    # least one list name we keep scrolling; the policy's end-detection + cap
    # decide when to stop.
    can_scroll = sum(1 for opt in options if opt.target != selected_target) >= 1

    return CharacterSelect(
        options=options,
        confirm_button=confirm_button,
        selected_name=selected_option.name,
        can_scroll=can_scroll,
        filter_button=profile.regions.get("character_select_filter_button"),
    )


# 同名角色多形态: 每行职业图标下方的形态文字 (普通=无, 第二形态=ANOTHER, 系列=COSMIC)。
_VARIANT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ANOTHER", ("ANOTHER", "ANOTHE", "NOTHER")),
    ("COSMIC", ("COSMIC", "COSMI", "OSMIC")),
)


def _normalize_variant(text: str) -> str:
    """OCR 文本规范化成形态标记 ANOTHER/COSMIC; 认不出返回 ''(普通形态)。
    容错: 大小写/空格无关, 0↔O 混淆, 以及缺首/尾字母的残读。"""
    up = "".join(text.upper().split()).replace("0", "O")
    for canon, keys in _VARIANT_KEYWORDS:
        if any(k in up for k in keys):
            return canon
    return ""


def _match_character_variants(
    names: list[tuple[str, int]],
    variant_tokens: list[tuple[str, int]],
    *,
    gap_min: int = 15,
    gap_max: int = 70,
) -> list[str]:
    """把形态文字关联到正上方的名字行。

    names: [(name, y_top), ...] (名字行顶 y); variant_tokens: [(raw_text, y_top), ...]
    (无法识别成角色名、但可能是形态文字的 token)。返回与 names 同序的形态标记列表 —
    名字行正下方 [gap_min, gap_max] 像素内若有可识别的形态文字则取之, 否则 ''(普通)。
    """
    out: list[str] = []
    for _name, ny in names:
        found = ""
        for raw, vy in variant_tokens:
            if gap_min <= vy - ny <= gap_max:
                canon = _normalize_variant(raw)
                if canon:
                    found = canon
                    break
        out.append(found)
    return out


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

    star_rect = profile.regions.get("blessing_star_filter_button")
    return BlessingChoice(
        options=options,
        confirm_button=profile.regions.get("blessing_choice_confirm_button"),
        selected_name=next(
            (option.name for option in options if option.name.endswith(f"_{selected_card_index:02d}")), None
        )
        if selected_card_index is not None
        else None,
        detail_sub_blessing_count=selected_sub_blessing_count,
        # 星标(收藏过滤)按钮 + 当前点亮状态(实机: 开=白底亮按钮, 关=深色)。
        star_filter_button=star_rect,
        star_filter_active=_star_filter_is_active(image, star_rect),
    )


def _star_filter_is_active(image: Image.Image | None, star_rect: Rect | None) -> bool:
    """星标按钮亮像素占比 > 40% = 过滤已开(实测: 开 81% / 关 0%)。"""
    if image is None or star_rect is None:
        return False
    try:
        box = image.convert("RGB").crop(
            (star_rect.x, star_rect.y, star_rect.x + star_rect.width, star_rect.y + star_rect.height)
        )
        pixels = list(box.getdata())
    except Exception:
        return False
    if not pixels:
        return False
    bright = sum(1 for r, g, b in pixels if r > 200 and g > 200 and b > 200)
    return bright / len(pixels) > 0.40


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


_FILTER_PROFESSIONS = ("坦克", "突击者", "游侠", "术师", "刺客", "辅助")


def parse_filter_dialog(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
    ocr: OcrEngine | None = None,
) -> FilterDialog | None:
    """筛选弹窗: 用 OCR bbox 在弹窗内容区定位职业按钮(点词=点按钮)。

    实机弹窗布局与 docx 不同(职业 3+3 两行), 固定坐标不可靠 —— 学
    parse_character_select_bbox 的做法, 找到目标词就点词中心(实测一点即中)。
    """
    confirm_button = profile.regions.get("filter_dialog_confirm_button")
    content = profile.regions.get("filter_dialog_content")
    if confirm_button is None or content is None:
        return None
    professions: dict[str, Rect] = {}
    if image is not None and ocr is not None:
        try:
            lines = ocr.read_lines(crop_region(image, content))
        except Exception:
            lines = []
        for line in lines:
            text = normalize_ocr_text(line.text)
            if not text:
                continue
            x1, y1, x2, y2 = line.box
            target = Rect(content.x + x1, content.y + y1, max(x2 - x1, 8), max(y2 - y1, 8))
            for word in _FILTER_PROFESSIONS:
                if word in text and word not in professions:
                    professions[word] = target
    return FilterDialog(
        profession_buttons=professions,
        confirm_button=confirm_button,
        reset_button=profile.regions.get("filter_dialog_reset_button"),
    )


def parse_main_screen(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> MainScreen | None:
    """游戏主界面: 取右上角菜单按钮(有无红色感叹号都点同一处)。"""
    menu_button = profile.regions.get("main_screen_menu_button")
    if menu_button is None:
        return None
    return MainScreen(menu_button=menu_button)


def parse_main_menu_panel(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> MainMenuPanel | None:
    """主界面菜单栏: 取「旅程」入口按钮。"""
    journey_entry = profile.regions.get("main_menu_panel_journey_entry")
    if journey_entry is None:
        return None
    return MainMenuPanel(journey_entry=journey_entry)


def parse_journey_start(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
    image: Image.Image | None = None,
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
    current_deck = None
    dots_rect = profile.regions.get("journey_start_deck_dots")
    if image is not None and dots_rect is not None:
        current_deck = _detect_active_deck_dot(image, dots_rect)
    return JourneyStart(
        start_button=start_button,
        auto_journey_button=profile.regions.get("journey_start_auto_journey_button"),
        arcana_slots=arcana_slots,
        current_deck=current_deck,
        previous_button=profile.regions.get("journey_start_previous_button"),
        next_button=profile.regions.get("journey_start_next_button"),
    )


def _detect_active_deck_dot(image: Image.Image, dots_rect: Rect) -> int | None:
    """5 个卡组指示圆点横条均分 5 段, 取最亮段为当前卡组(1-5)。

    亮点是白色高亮、暗点是半透明灰; 最亮段与平均的差太小说明检测不可信
    (动画/截图时机), 返回 None 让决策层跳过卡组切换而不是乱点。
    """
    try:
        strip = image.crop(
            (dots_rect.x, dots_rect.y, dots_rect.x + dots_rect.width, dots_rect.y + dots_rect.height)
        ).convert("L")
    except Exception:
        return None
    if strip.width < 5 or strip.height < 1:
        return None
    segment = strip.width // 5
    means: list[float] = []
    for i in range(5):
        box = strip.crop((i * segment, 0, (i + 1) * segment, strip.height))
        pixels = list(box.getdata())
        means.append(sum(pixels) / len(pixels) if pixels else 0.0)
    brightest = max(range(5), key=lambda i: means[i])
    rest = [m for i, m in enumerate(means) if i != brightest]
    if not rest or means[brightest] - (sum(rest) / len(rest)) < 25:
        return None
    return brightest + 1


def parse_support_picker(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> SupportPicker | None:
    """支援卡选择界面: 「可借用」标签 OCR 到才算可接好友卡。"""
    back_button = profile.regions.get("support_picker_back_button")
    if back_button is None:
        return None
    texts = {item.name: item.text for item in region_texts}
    has_borrow = "可借用" in texts.get("support_picker_borrow_anchor", "")
    return SupportPicker(
        back_button=back_button,
        friend_button=profile.regions.get("support_picker_friend_button"),
        has_borrow=has_borrow,
    )


def parse_support_friend_list(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> SupportFriendList | None:
    """好友支援卡墙: 第一排 6 张卡的名牌 OCR + 卡中心点击位。"""
    texts = {item.name: item.text for item in region_texts}
    cards: list[SupportFriendCard] = []
    for index in range(1, 7):
        target = profile.regions.get(f"support_friend_card_{index}")
        if target is None:
            continue
        name = normalize_ocr_text(texts.get(f"support_friend_name_{index}", ""))
        if name:
            cards.append(SupportFriendCard(name=name, target=target))
    if not cards and profile.regions.get("support_friend_card_1") is None:
        return None
    return SupportFriendList(
        cards=cards,
        back_button=profile.regions.get("support_friend_back_button"),
    )


def parse_support_card_detail(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> SupportCardDetail | None:
    select_button = profile.regions.get("support_card_detail_select")
    if select_button is None:
        return None
    return SupportCardDetail(select_button=select_button)


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
    confirm_text = texts.get("event_fast_forward_confirm_button", "")
    has_title = contains_any_text(title, ("\u4e8b\u4ef6\u5feb\u8f6c\u8bbe\u5b9a", "fast"))
    has_confirm_button_text = contains_any_text(confirm_text, ("\u51b3\u5b9a", "\u786e\u8ba4", "confirm"))
    if title and not has_title:
        return None
    if not has_title and not has_confirm_button_text:
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

    # 阿尔克那事件: 属性提升的结果展示, 右上 skip 按键对它无效(实机点了画面不动→死循环),
    # 必须点屏幕中心推进(用户告知)。event_label/title 含"阿尔克那"时把推进点设为屏幕中心。
    # (这类无选项的事件会被 classify_hybrid 当成可 skip 的 dialogue, 故在此拦下。)
    arcana_label = texts.get("dialogue_journey_event_label", "") + texts.get("dialogue_journey_title", "")
    center = profile.regions.get("screen_center_button")
    if center is not None and contains_any_text(arcana_label, ("阿尔克那", "尔克那", "克那")):
        return DialogueScene(skip_button=center, variant="arcana_center")

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
        card_text = texts.get(key, "")
        if name is not None or score is not None:
            options.append(RelicOption(
                name=name or f"unknown_relic_{index}",
                score=score,
                target=target,
                attribute=_relic_attribute_from_name(name),
                is_team="队员全体" in card_text,  # 队员全体 = 组合圣遗物
            ))

    if not options:
        # 3-card parse found nothing → this "选择奖励" is the inventory-GRID variant
        # (pick a relic from 持有道具, not a 3-card row). We can't read the "持有道具"
        # label to detect it — that panel region (relic_choice_card_1) is larger than
        # the live loop's OCR max_area and gets skipped — so "no cards parsed on a relic
        # screen" IS the grid signal. Select the first/topmost (NEW/selected) item and
        # confirm via 选择完成, reusing the two-step _pending_relic confirm.
        grid_cell = profile.regions.get("relic_choice_grid_cell_1")
        confirm = profile.regions.get("relic_choice_confirm_button")
        if grid_cell is not None and confirm is not None:
            return RelicChoice(
                options=[RelicOption(name="held_item_1", score=0, target=grid_cell)],
                confirm_button=confirm,
            )
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
    # Unknown relic: keep the raw OCR name (cleaned) instead of returning None.
    # This stops non-first-round relics from being labelled "unknown_relic_N" and,
    # crucially, keeps the highlighted/selected card (whose name OCRs slightly
    # garbled) from being dropped from the options list.
    cleaned = (text or "").strip()
    return cleaned or None


# 部位名(圣遗物名字尾部)→ 战斗属性. 跨系列固定.
_RELIC_PART_ATTRIBUTE = {
    "手套": "attack",
    "帽子": "crit_rate",
    "项链": "crit_dmg",
    "项炼": "crit_dmg",
    "裤子": "defense",
    "铠甲": "hp",
    "胸甲": "hp",
    "眼镜": "hit",
    "鞋子": "speed",
    "披风": "resist",
}


def _relic_attribute_from_name(name: str | None) -> str | None:
    """按部位名(名字尾部)映射出战斗属性; 认不出返回 None."""
    if not name:
        return None
    for part, attr in _RELIC_PART_ATTRIBUTE.items():
        if part in name:
            return attr
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

    # D-DAY (\u8bc4\u9274\u6218\u65e5) hub: the right column swaps \u8bad\u7ec3/\u59d4\u6258/\u4f11\u606f for \u8bc4\u9274\u6218(top) +
    # \u4ea4\u6613(bottom). When those buttons OCR there, surface both so the policy goes
    # \u4ea4\u6613 first (\u6253\u8fc7\u8bc4\u9274\u6218\u4ea4\u6613\u5c31\u6d88\u5931), then \u8bc4\u9274\u6218. Detection keys off the button
    # text so a normal hub (\u8bad\u7ec3/\u4f11\u606f there) leaves these None.
    is_dday = contains_any_text(
        texts.get("training_hub_rating_battle", ""), ("\u8bc4\u9274\u6218", "\u9274\u6218")
    ) or contains_any_text(texts.get("training_hub_trading", ""), ("\u4ea4\u6613",))
    rating_battle_button = profile.regions.get("training_hub_rating_battle") if is_dday else None
    trading_button = profile.regions.get("training_hub_trading") if is_dday else None

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
        rating_battle_button=rating_battle_button,
        trading_button=trading_button,
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
    back_button = profile.regions.get("top_back_button")

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
        # its presence is a reliable "this card is selected" signal. When it is NOT
        # shown the rate is UNKNOWN (None), never 0 — a 0 here would read as "safe 0%"
        # and let the policy gamble on an un-inspected, possibly ~99%-fail card.
        selected = card_fail is not None
        fail_rate = card_fail
        stat_gain = parse_first_int(gain_text) or 0

        ring = "none"
        if image is not None:
            # 逐卡彩圈区域优先(training_select_ring_{attr}, 实机帧标定后精确);
            # 未配置回退整块面板检测(旧行为: 5 卡同值, 只能反映"有彩圈出现")。
            ring_rect = profile.regions.get(f"training_select_ring_{attr}") or profile.regions.get(
                "training_select_ring_detect"
            )
            if ring_rect is not None:
                ring_signal = RingColorDetector().detect(crop_region(image, ring_rect))
                ring = ring_signal.name

        icon_count = _count_training_icons(image, profile, attr)

        choices.append(
            TrainingChoice(
                name=recognized_name,
                stat_gain=stat_gain,
                ring=ring,
                fail_rate=fail_rate,
                target=card_rect,
                attr=attr,
                icon_count=icon_count,
                selected=selected,
                confirm_button=confirm_button,
                back_button=back_button,
            )
        )

    if not choices:
        return None
    return choices


def _count_training_icons(
    image: Image.Image | None, profile: RegionProfile, attr: str
) -> int:
    """数某行训练上的支援卡人头(卡面纵列小头像)。

    区域 training_select_icons_{attr} 框住该行的人头列(实机帧校准后填),
    在列内自上而下按等距槽位用 support_cards.has_card_icon 判定, 首个空槽停。
    区域未配置 / 无图像 → 0(前期人头策略自动不触发, 回退检视器)。
    """
    if image is None:
        return 0
    col_rect = profile.regions.get(f"training_select_icons_{attr}")
    if col_rect is None:
        return 0
    try:
        from starsavior_trainer.support_cards import has_card_icon

        column = crop_region(image, col_rect)
        slots = 8
        slot_h = column.height // slots
        if slot_h < 4:
            return 0
        count = 0
        for slot in range(slots):
            patch = column.crop((0, slot * slot_h, column.width, (slot + 1) * slot_h))
            if has_card_icon(patch):
                count += 1
            else:
                break
        return count
    except Exception:
        logger.debug("training icon count failed for %s", attr, exc_info=True)
        return 0


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
        lodging=profile.regions.get("rest_submenu_option_2"),
        confirm_button=profile.regions.get("rest_submenu_confirm_button"),
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

    # 对话式事件选项变体(右侧选项行, 无常规事件面板; 2026-06-12 实跑发现:
    # 委托失败后的剧情分支)。带锁的选项 OCR 一般会带 🔒/数字噪声, 仍按文本
    # 入列, 由事件库/关键词规则去选安全项。
    if not options:
        for idx in (1, 2):
            target = profile.regions.get(f"event_choice_side_{idx}")
            if target is None:
                continue
            side_text = texts.get(f"event_choice_side_{idx}", "")
            if side_text.strip():
                options.append(
                    EventOption(text=side_text.strip(), target=target, event_title=event_title or "side_event")
                )

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
    # \u5bf9\u8bdd\u5f0f\u4e8b\u4ef6\u9009\u9879\u53d8\u4f53: \u53f3\u4fa7\u9009\u9879\u884c\u6709\u5b57\u5373\u8ba4(\u4e0e classifier \u7b7e\u540d\u4e00\u81f4)\u3002
    if len(texts.get("event_choice_side_1", "").strip()) >= 2:
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
    # 建议综合等级只在中央详情区显示当前选中委托的值 (如 "RANK 17"); 角色综合等级在
    # 左上 ("RANK 21")。两者都是数字, 供检视器逐个点开读建议等级、选≤角色等级的最高阶。
    suggested_rank = parse_rank_number(texts.get("commission_select_suggested_rank", ""))
    character_rank = parse_rank_number(texts.get("commission_select_character_rank", ""))
    return CommissionChoice(
        options=options,
        accept_button=accept_btn,
        back_button=back_btn,
        selected_suggested_rank=suggested_rank,
        character_rank=character_rank,
    )


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
) -> ShopScene | None:
    """Read Journey Trading (交易) items: one ShopItem per defined row.

    The right-side list OCRs unreliably (small text over a textured/transparent
    panel, with strikethrough prices), and the buy decision keys off each item's
    *effect* — which only shows in the centre detail panel once the item is
    selected, so the shop inspector reads it by clicking each row. We therefore
    return one clickable item per ``shop_item_N`` row regardless of whether its
    name/price OCR'd; name/price are filled best-effort for logging/identity. The
    selected item's effect detail is read separately (``shop_detail_effect``) and
    attributed to the clicked row by the inspector.
    """
    texts = {item.name: item.text for item in region_texts}

    items: list[ShopItem] = []
    for idx in range(1, 6):
        target = profile.regions.get(f"shop_item_{idx}")
        if target is None:
            continue
        name = texts.get(f"shop_item_{idx}_name", "").strip()
        price = parse_first_int(texts.get(f"shop_item_{idx}_price", ""))
        button = profile.regions.get(f"shop_item_{idx}_button")
        click_target = button if button is not None else target
        items.append(ShopItem(name=name, price=price if price is not None else 0, target=click_target))

    if not items:
        return None
    return ShopScene(
        items=tuple(items),
        # The selected item's effect detail (centre panel) — only this needs OCR;
        # the shop inspector attributes it to the row it clicked last turn.
        selected_effect=texts.get("shop_detail_effect", "").strip(),
        buy_button=profile.regions.get("shop_buy_button"),
        back_button=profile.regions.get("shop_back_button"),
    )


# ---------------------------------------------------------------------------
# Region Move parser
# ---------------------------------------------------------------------------


def parse_region_move(
    region_texts: Iterable[RegionText],
    profile: RegionProfile,
) -> Rect | None:
    """Detect the region-move screen and return the rect to click next.

    The real \u5217\u8f66\u6708\u53f0 (train-station) region-move is a two-step flow: a destination
    list (e.g. \u963f\u5361\u519c) on the right; clicking a destination shows its detail card and
    a \u524d\u5f80 (go) button at the bottom-right; \u524d\u5f80 travels there. So:
      - \u524d\u5f80 present  \u2192 return the \u524d\u5f80 button (a destination is selected \u2192 travel).
      - otherwise     \u2192 return the first destination row (select it first).
    Falls back to the older single \u79fb\u52a8-button screen for backward compatibility.
    """
    texts = {item.name: item.text for item in region_texts}

    # \u5217\u8f66\u6708\u53f0 region-move (anchors: \u5730\u533a\u79fb\u52a8 + \u5217\u8f66\u6708\u53f0).
    anchor = texts.get("region_move_anchor_title", "")
    station = texts.get("region_move_station_title", "")
    if contains_any_text(anchor, ("\u5730\u533a\u79fb\u52a8", "\u533a\u79fb\u52a8", "\u5730\u533a")) and contains_any_text(
        station, ("\u5217\u8f66\u6708\u53f0", "\u8f66\u6708\u53f0", "\u6708\u53f0")
    ):
        if contains_any_text(texts.get("region_move_go_button", ""), ("\u524d\u5f80", "\u51fa\u53d1", "\u524d\u4f4f")):
            go = profile.regions.get("region_move_go_button")
            if go is not None:
                return go
        dest = profile.regions.get("region_move_destination_1")
        if dest is not None:
            return dest
        return None

    # Backward-compat: older single \u79fb\u52a8-button region-move screen.
    move_rect = profile.regions.get("region_move_button")
    if move_rect is not None and contains_any_text(texts.get("region_move_button_text", ""), ("\u79fb\u52a8", "move")):
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

    # 跳过战斗 二次确认框: 点「跳过战斗」后弹出"将一并跳过评鉴战前的故事…确定要跳过评鉴
    # 战斗吗?"(取消 / 蓝色「跳过战斗」)。必须点框内蓝色「跳过战斗」确认 —— 底层按钮被遮住,
    # 再点它只会死循环。靠「取消」按钮区分(基础评鉴战确认界面那一侧是「开始委托」, 无取消)。
    skip_confirm_button = profile.regions.get("battle_skip_confirm_button")
    if (
        skip_confirm_button is not None
        and contains_any_text(texts.get("battle_skip_confirm_cancel", ""), ("取消",))
        and contains_any_text(texts.get("battle_skip_confirm_button", ""), ("跳过", "战斗"))
    ):
        return BattleScene(skip_button=skip_confirm_button, confirm_button=None, confirm_active=False)

    # 基础评鉴战 entry confirm (是否要进行评鉴战?): always pick 跳过战斗 — skip the
    # battle and take the result instantly (开始委托 actually fights). confirm_active
    # stays False so decide_battle clicks this skip button, not a confirm button.
    skip_battle_button = profile.regions.get("battle_skip_battle_button")
    if skip_battle_button is not None and (
        contains_any_text(texts.get("battle_skip_battle_button", ""), ("跳过战斗", "跳过"))
        or contains_any_text(texts.get("battle_confirm_title", ""), ("评鉴战", "鉴战"))
    ):
        return BattleScene(skip_button=skip_battle_button, confirm_button=None, confirm_active=False)

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


def _count_detail_sub_blessings(profile: RegionProfile, image: Image.Image | None) -> int:
    if image is None:
        return 0
    count = 0
    for index in range(1, 4):
        rect = profile.regions.get(f"blessing_choice_detail_sub_{index}")
        if rect is not None and _detail_sub_blessing_slot_filled(rect, image):
            count += 1
    return count


def _or_none(text: str | None) -> str | None:
    t = (text or "").strip()
    return t if t else None


def _ocr_int_token_to_int(token: str) -> int:
    cleaned = token.translate(str.maketrans({"o": "0", "l": "1", "i": "1", "s": "5"}))
    return int(cleaned.replace(",", ""))
