from __future__ import annotations

import colorsys
from dataclasses import dataclass

from PIL import Image

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
