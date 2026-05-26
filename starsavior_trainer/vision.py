from __future__ import annotations

import colorsys
from dataclasses import dataclass

from PIL import Image

from starsavior_trainer.image_regions import crop_region
from starsavior_trainer.logging_setup import get_logger
from starsavior_trainer.models import Rect

logger = get_logger("vision")

_CV2_IMPORT_FAILED = False


@dataclass(frozen=True)
class ColorSignal:
    name: str
    confidence: float
    coverage: float


class RingColorDetector:
    """Detect coarse training ring colors in a cropped region."""

    def detect(self, image: Image.Image) -> ColorSignal:
        global _CV2_IMPORT_FAILED
        if _CV2_IMPORT_FAILED:
            return _detect_with_pil(image)
        try:
            return _detect_with_cv2(image)
        except ImportError:
            _CV2_IMPORT_FAILED = True
            return _detect_with_pil(image)


class BlueButtonDetector:
    """Detect whether an action button is the enabled blue style."""

    def detect(self, image: Image.Image) -> ColorSignal:
        rgb = image.convert("RGB")
        pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        pixels = list(pixel_data)
        total = max(len(pixels), 1)
        # Lower saturation threshold — game uses muted blue-gray buttons (s≈0.22).
        coverage = _pil_coverage(pixels, 180, 250, 0.18, 0.30, total)
        if coverage < 0.03:
            return ColorSignal("inactive", 1.0 - coverage, coverage)
        return ColorSignal("active_blue", min(coverage * 6, 1.0), coverage)


def _detect_with_cv2(image: Image.Image) -> ColorSignal:
    import cv2
    import numpy as np

    rgb = np.array(image.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    total = max(int(hsv.shape[0] * hsv.shape[1]), 1)

    signals = {
        "rainbow": _coverage(hsv, (135, 45, 80), (175, 255, 255), total),
        "gold": _coverage(hsv, (18, 80, 90), (42, 255, 255), total),
        "blue": _coverage(hsv, (90, 60, 80), (125, 255, 255), total),
    }
    return _best_signal(signals)


def _detect_with_pil(image: Image.Image) -> ColorSignal:
    rgb = image.convert("RGB")
    pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
    pixels = list(pixel_data)
    total = max(len(pixels), 1)
    signals = {
        "rainbow": _pil_coverage(pixels, 270, 350, 0.18, 0.31, total),
        "gold": _pil_coverage(pixels, 36, 84, 0.31, 0.35, total),
        "blue": _pil_coverage(pixels, 180, 250, 0.24, 0.31, total),
    }
    return _best_signal(signals)


def _best_signal(signals: dict[str, float]) -> ColorSignal:
    name, coverage = max(signals.items(), key=lambda item: item[1])
    if coverage < 0.01:
        return ColorSignal("none", 1.0 - coverage, coverage)
    return ColorSignal(name, min(coverage * 10, 1.0), coverage)


def _coverage(hsv, lower: tuple[int, int, int], upper: tuple[int, int, int], total: int) -> float:
    import cv2
    import numpy as np

    mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
    return float(cv2.countNonZero(mask)) / total


def _pil_coverage(
    pixels: list[tuple[int, int, int]],
    hue_min: int,
    hue_max: int,
    saturation_min: float,
    value_min: float,
    total: int,
) -> float:
    count = 0
    for red, green, blue in pixels:
        hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        hue_degrees = hue * 360
        if hue_min <= hue_degrees <= hue_max and saturation >= saturation_min and value >= value_min:
            count += 1
    return count / total


# ===========================================================================
# Pixel / color detection (consolidated here from screen_reader.py).
# Thresholds below are extracted verbatim from the original functions — the
# numbers and comparison conditions are UNCHANGED, only named and documented.
# ===========================================================================

# 祝福槽是否已装备：裁剪区灰度图的均值 / 标准差下限（已装备的槽更亮、对比更高）。
BLESSING_SLOT_FILLED_MEAN_MIN = 85
BLESSING_SLOT_FILLED_STDDEV_MIN = 45

# 卡片高亮亮边：判定一个像素属于"亮白描边"的 RGB 分量下限（选中卡片有亮描边）。
BRIGHT_BORDER_R_MIN = 220
BRIGHT_BORDER_G_MIN = 210
BRIGHT_BORDER_B_MIN = 190

# 详情面板子祝福槽是否填充：可见像素(r+g+b 之和)下限，以及可见像素占比下限。
DETAIL_SUB_VISIBLE_SUM_MIN = 220
DETAIL_SUB_FILLED_RATIO_MIN = 0.20

# 红字检测（委托"受理讨伐委托"红字横幅等）：红色像素条件 r>R_MIN 且 g,b<GB_MAX，及占比下限。
RED_TEXT_R_MIN = 180
RED_TEXT_GB_MAX = 100
RED_TEXT_RATIO_MIN = 0.05

# 黄字检测（训练主界面商店"到货"黄字提醒）：黄色像素条件 r>R_MIN 且 g>G_MIN 且 b<B_MAX，及占比下限。
YELLOW_TEXT_R_MIN = 180
YELLOW_TEXT_G_MIN = 130
YELLOW_TEXT_B_MAX = 100
YELLOW_TEXT_RATIO_MIN = 0.03


def is_blue_region(rect: Rect, image: Image.Image | None) -> bool:
    if image is None:
        return False
    signal = BlueButtonDetector().detect(crop_region(image, rect))
    return signal.name == "active_blue"


def is_blessing_slot_filled(rect: Rect, image: Image.Image | None) -> bool:
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
        return mean >= BLESSING_SLOT_FILLED_MEAN_MIN and stddev >= BLESSING_SLOT_FILLED_STDDEV_MIN
    except Exception as e:
        logger.debug(f"[is_blessing_slot_filled] pixel analysis failed: {e}")
        return False


def card_highlight_score(rect: Rect, image: Image.Image) -> float:
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
        return max(bright_border_ratio(outside_top), bright_border_ratio(outside_left), bright_border_ratio(inside_left))
    except Exception as e:
        logger.debug(f"[card_highlight_score] highlight analysis failed: {e}")
        return 0.0


def bright_border_ratio(image: Image.Image) -> float:
    pixel_data = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    pixels = list(pixel_data)
    if not pixels:
        return 0.0
    bright_border = sum(
        1 for r, g, b in pixels if r > BRIGHT_BORDER_R_MIN and g > BRIGHT_BORDER_G_MIN and b > BRIGHT_BORDER_B_MIN
    )
    return bright_border / len(pixels)


def detail_sub_blessing_slot_filled(rect: Rect, image: Image.Image) -> bool:
    try:
        rgb = crop_region(image, rect).convert("RGB")
        pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        pixels = list(pixel_data)
        if not pixels:
            return False
        visible_pixels = sum(1 for r, g, b in pixels if r + g + b > DETAIL_SUB_VISIBLE_SUM_MIN)
        return visible_pixels / len(pixels) >= DETAIL_SUB_FILLED_RATIO_MIN
    except Exception as e:
        logger.debug(f"[detail_sub_blessing_slot_filled] pixel analysis failed: {e}")
        return False


def detect_red_text(image: Image.Image) -> bool:
    """Crude red-text detection: check if enough red-ish pixels exist."""
    try:
        rgb = image.convert("RGB")
        pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        pixels = list(pixel_data)
        total = max(len(pixels), 1)
        red_count = 0
        for r, g, b in pixels:
            if r > RED_TEXT_R_MIN and g < RED_TEXT_GB_MAX and b < RED_TEXT_GB_MAX:
                red_count += 1
        return red_count / total > RED_TEXT_RATIO_MIN
    except Exception as e:
        logger.debug(f"[detect_red_text] red detection failed: {e}")
        return False


def detect_yellow_text(image: Image.Image) -> bool:
    """Crude yellow-text detection for training-hub shop alerts."""
    try:
        rgb = image.convert("RGB")
        pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        pixels = list(pixel_data)
        total = max(len(pixels), 1)
        yellow_count = 0
        for r, g, b in pixels:
            if r > YELLOW_TEXT_R_MIN and g > YELLOW_TEXT_G_MIN and b < YELLOW_TEXT_B_MAX:
                yellow_count += 1
        return yellow_count / total > YELLOW_TEXT_RATIO_MIN
    except Exception as e:
        logger.debug(f"[detect_yellow_text] yellow detection failed: {e}")
        return False
