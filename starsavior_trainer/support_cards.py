"""Support-card (阿尔克那) visual detection ported from the legacy project.

Ported from ``Starsavior-master`` (OpenCV/numpy BGR pipeline) into this
project's PIL-first style (see ``vision.py``):

- 黄色羁绊条检测      ← ``src/arcanum.py`` ``_detect_yellow_bar`` + module constants
- 图标存在性/计数     ← ``src/icon_counter.py`` ``count_circular_icons``
- 属性图标颜色分类    ← ``src/arcanum.py`` ``_detect_icon_by_color``
- 闪光(flash)训练检测 ← ``src/trainer.py`` ``_detect_flash_training``
- 图标优先级规则      ← ``src/icon_counter.py`` ``apply_priority_rule``

All functions take already-cropped PIL images (this project's screenshot
pipeline is PIL) and are pure: no OCR, no screen classification, no clicking.
NumPy is used when importable, otherwise a pure-PIL per-pixel fallback runs —
the same dual-path pattern as ``vision.py`` (which falls back cv2 → PIL).

颜色阈值单位说明: 所有 HSV 常量保持源项目的 OpenCV 单位原值不动 ——
H ∈ [0, 180) (= 角度/2)、S/V ∈ [0, 255]。本模块内部把 RGB 转成同一单位再比较,
因此阈值可与源文件逐行对照。cv2.inRange 是闭区间, 这里同样按闭区间实现。

与源实现的已知差异(刻意保留/记录):
- 源 ``_detect_yellow_bar`` 在算占比前做了一次 3x3 膨胀(dilate); 这里在两条
  路径(NumPy/PIL)都用 3x3 八邻域 OR 等价实现, 行为一致。
- 源色彩转换走 BGR→HSV, 这里走 RGB→HSV; 对同一画面两者得到的 HSV 相同,
  阈值可直接复用。
"""

from __future__ import annotations

import colorsys
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image

from starsavior_trainer.logging_setup import get_logger

logger = get_logger("support_cards")

_NUMPY_IMPORT_FAILED = False


# ===========================================================================
# Thresholds — copied verbatim from the legacy project, units unchanged.
# ===========================================================================

# --- 黄色羁绊条 (源: arcanum.py YELLOW_HSV_LOWER / YELLOW_HSV_UPPER) ---
# 羁绊条达到黄色 = 高羁绊、可触发闪光训练。H 18-38 (≈36°-76°), S≥80, V≥100。
BOND_YELLOW_HSV_LOWER = (18.0, 80.0, 100.0)
BOND_YELLOW_HSV_UPPER = (38.0, 255.0, 255.0)

# 黄色像素(膨胀后)占比超过此值认为羁绊条已黄 (源: arcanum.py BOND_YELLOW_RATIO)。
BOND_YELLOW_RATIO = 0.35

# --- 闪光训练按钮 (源: trainer.py _detect_flash_training) ---
# 方法1: "浅黄/暖白" 像素 H 12-45 (≈24°-90°), S≥35, V≥130; 占比 > 0.03 判闪光。
FLASH_HSV_LOWER = (12.0, 35.0, 130.0)
FLASH_HSV_UPPER = (45.0, 255.0, 255.0)
FLASH_RATIO_MIN = 0.03

# 方法2 (仅多行对比时可用): 某行按钮区的饱和度均值显著高于全体均值 → 闪光。
# 条件: s_mean > 全体均值 + FLASH_SAT_DELTA 且 s_mean > FLASH_SAT_MIN。
FLASH_SAT_DELTA = 8.0
FLASH_SAT_MIN = 50.0

# --- 圆形图标统计判定 (源: icon_counter.py count_circular_icons 内联阈值) ---
# 彩色图标: satMean > 40 且 valMean > 70 且 satStd > 25, 再按 satMean 细分:
#   satMean < 75 → 要求 satStd > 35; 否则要求 satStd > 40。
ICON_COLOR_SAT_MEAN_MIN = 40.0
ICON_COLOR_VAL_MEAN_MIN = 70.0
ICON_COLOR_SAT_STD_MIN = 25.0
ICON_COLOR_SAT_MEAN_SPLIT = 75.0
ICON_COLOR_SAT_STD_LOW_MIN = 35.0
ICON_COLOR_SAT_STD_HIGH_MIN = 40.0
# 灰色/高亮立绘图标: valMean > 135 且 valStd > 30。
ICON_GRAY_VAL_MEAN_MIN = 135.0
ICON_GRAY_VAL_STD_MIN = 30.0

# --- 图标槽几何, 相对于训练界面截图的百分比 (源: icon_counter.py 模块常量) ---
# 图标列在画面右侧 x≈73%, 自 y≈13% 起每 8% 一个槽, 最多 8 个; 采样半径为宽度 1.5%。
ICON_CENTER_X = 0.73
ICON_START_Y = 0.13
ICON_SPACING = 0.08
MAX_ICON_SLOTS = 8
ICON_CHECK_RADIUS = 0.015

# --- 属性图标 HSV 主色调 (源: arcanum.py ATTRIBUTE_ICON_COLORS) ---
# 属性ID → (lower, upper)。1=力量(红, 需 wrap-around), 2=生命(橙/粉/白),
# 3=韧性(绿/黄绿), 4=命中(蓝), 5=保护(紫/品红)。
ATTRIBUTE_ICON_HSV: dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    1: ((0.0, 40.0, 60.0), (10.0, 255.0, 255.0)),
    2: ((0.0, 20.0, 100.0), (25.0, 150.0, 255.0)),
    3: ((30.0, 50.0, 40.0), (80.0, 255.0, 200.0)),
    4: ((100.0, 50.0, 40.0), (130.0, 255.0, 200.0)),
    5: ((140.0, 40.0, 30.0), (175.0, 255.0, 200.0)),
}
# 命中率门槛: 范围内像素占比需 > 0.03 才参与评分 (源: _detect_icon_by_color)。
ATTRIBUTE_ICON_RATIO_MIN = 0.03
# 力量(红色) H 的 wrap-around 补充区间 [160, 180] (源: _detect_icon_by_color)。
STRENGTH_ATTRIBUTE_ID = 1
RED_WRAP_HUE = (160.0, 180.0)

# --- 卡位裁剪内的子区域 (源: arcanum.py ArcanumDetector.__init__ 默认配置) ---
# 均为 (x_off, y_off, w, h) 占单张卡位裁剪图的比例。
# 左上角属性图标: icon_x_offset=0.05, icon_y_offset=0.02, icon_w=0.30, icon_h=0.18。
CARD_ICON_BOX = (0.05, 0.02, 0.30, 0.18)
# 头像下方羁绊条: bond_bar_x_offset=0.10, bond_bar_y_offset=0.82,
#                bond_bar_w=0.80, bond_bar_h=0.08。
CARD_BOND_BAR_BOX = (0.10, 0.82, 0.80, 0.08)


# ===========================================================================
# Result type
# ===========================================================================


@dataclass(frozen=True)
class SupportCardSignal:
    """Visual signals extracted from one support-card slot crop."""

    bond_ratio: float  # 羁绊条裁剪区内黄色覆盖率 (0.0-1.0, 含 3x3 膨胀)
    bond_yellow: bool  # bond_ratio >= BOND_YELLOW_RATIO (高羁绊/快满)
    has_icon: bool  # 卡位左上角图标区是否检测到图标
    is_flash: bool  # 配套训练按钮是否闪光 (未提供按钮裁剪图时恒为 False)


# ===========================================================================
# HSV primitives — numpy fast path with pure-PIL fallback (vision.py pattern).
# ===========================================================================


def _mask_stats(
    image: Image.Image,
    lower: tuple[float, float, float],
    upper: tuple[float, float, float],
    *,
    red_wrap_hue: tuple[float, float] | None = None,
    dilate: bool = False,
) -> tuple[float, float]:
    """Coverage of HSV-in-range pixels and the mean saturation of those pixels.

    Returns ``(ratio, mean_masked_saturation)``; the optional 3x3 dilation
    (源 _detect_yellow_bar 的 cv2.dilate) only affects the ratio.
    """
    global _NUMPY_IMPORT_FAILED
    if not _NUMPY_IMPORT_FAILED:
        try:
            return _mask_stats_numpy(image, lower, upper, red_wrap_hue, dilate)
        except ImportError:
            _NUMPY_IMPORT_FAILED = True
    return _mask_stats_pil(image, lower, upper, red_wrap_hue, dilate)


def _sv_stats(image: Image.Image) -> tuple[float, float, float, float]:
    """Mean/population-std of saturation and value: (s_mean, s_std, v_mean, v_std)."""
    global _NUMPY_IMPORT_FAILED
    if not _NUMPY_IMPORT_FAILED:
        try:
            return _sv_stats_numpy(image)
        except ImportError:
            _NUMPY_IMPORT_FAILED = True
    return _sv_stats_pil(image)


def _hsv_channels_numpy(image: Image.Image):
    """RGB image → float32 (h, s, v) arrays in OpenCV units (H<180, S/V≤255)."""
    import numpy as np

    arr = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maxc = arr.max(axis=-1)
    minc = arr.min(axis=-1)
    delta = maxc - minc

    chromatic = delta > 1e-12
    safe_delta = np.where(chromatic, delta, 1.0)
    hue = np.zeros_like(maxc)
    r_max = chromatic & (maxc == r)
    g_max = chromatic & (maxc == g) & ~r_max
    b_max = chromatic & ~r_max & ~g_max
    hue[r_max] = np.mod((g - b)[r_max] / safe_delta[r_max], 6.0)
    hue[g_max] = (b - r)[g_max] / safe_delta[g_max] + 2.0
    hue[b_max] = (r - g)[b_max] / safe_delta[b_max] + 4.0

    h_cv = hue * 30.0  # sector*60 = 角度, OpenCV H = 角度/2
    s_cv = np.where(maxc > 1e-12, delta / np.maximum(maxc, 1e-12), 0.0) * 255.0
    v_cv = maxc * 255.0
    return h_cv, s_cv, v_cv


def _pixel_hsv_cv(red: int, green: int, blue: int) -> tuple[float, float, float]:
    """One RGB pixel → OpenCV-unit HSV via colorsys (PIL fallback path)."""
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    return hue * 180.0, saturation * 255.0, value * 255.0


def _mask_stats_numpy(image, lower, upper, red_wrap_hue, dilate):
    import numpy as np

    h_cv, s_cv, v_cv = _hsv_channels_numpy(image)
    if h_cv.size == 0:
        return 0.0, 0.0

    lo_h, lo_s, lo_v = lower
    up_h, up_s, up_v = upper
    hue_ok = (h_cv >= lo_h) & (h_cv <= up_h)
    if red_wrap_hue is not None:
        hue_ok |= (h_cv >= red_wrap_hue[0]) & (h_cv <= red_wrap_hue[1])
    mask = hue_ok & (s_cv >= lo_s) & (s_cv <= up_s) & (v_cv >= lo_v) & (v_cv <= up_v)

    count = int(mask.sum())
    mean_masked_s = float(s_cv[mask].mean()) if count else 0.0

    ratio_mask = _dilate3x3_numpy(mask) if (dilate and count) else mask
    ratio = float(ratio_mask.sum()) / mask.size
    return ratio, mean_masked_s


def _dilate3x3_numpy(mask):
    """3x3 全 1 核膨胀一次 (等价 cv2.dilate(kernel=ones((3,3)), iterations=1))。"""
    import numpy as np

    height, width = mask.shape
    padded = np.zeros((height + 2, width + 2), dtype=bool)
    padded[1:-1, 1:-1] = mask
    out = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            out |= padded[dy : dy + height, dx : dx + width]
    return out


def _mask_stats_pil(image, lower, upper, red_wrap_hue, dilate):
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
    pixels = list(pixel_data)
    if not pixels:
        return 0.0, 0.0

    lo_h, lo_s, lo_v = lower
    up_h, up_s, up_v = upper
    flags: list[bool] = []
    masked_count = 0
    masked_s_sum = 0.0
    for red, green, blue in pixels:
        h_cv, s_cv, v_cv = _pixel_hsv_cv(red, green, blue)
        in_hue = lo_h <= h_cv <= up_h
        if not in_hue and red_wrap_hue is not None:
            in_hue = red_wrap_hue[0] <= h_cv <= red_wrap_hue[1]
        hit = in_hue and lo_s <= s_cv <= up_s and lo_v <= v_cv <= up_v
        flags.append(hit)
        if hit:
            masked_count += 1
            masked_s_sum += s_cv

    mean_masked_s = masked_s_sum / masked_count if masked_count else 0.0
    hit_count = _dilated_count_pil(flags, width, height) if (dilate and masked_count) else masked_count
    return hit_count / len(pixels), mean_masked_s


def _dilated_count_pil(flags: list[bool], width: int, height: int) -> int:
    """Count of pixels covered after a 3x3 dilation of the boolean mask."""
    hit = 0
    for y in range(height):
        for x in range(width):
            found = False
            for dy in (-1, 0, 1):
                ny = y + dy
                if not 0 <= ny < height:
                    continue
                row = ny * width
                for dx in (-1, 0, 1):
                    nx = x + dx
                    if 0 <= nx < width and flags[row + nx]:
                        found = True
                        break
                if found:
                    break
            if found:
                hit += 1
    return hit


def _sv_stats_numpy(image):
    _, s_cv, v_cv = _hsv_channels_numpy(image)
    if s_cv.size == 0:
        return 0.0, 0.0, 0.0, 0.0
    return float(s_cv.mean()), float(s_cv.std()), float(v_cv.mean()), float(v_cv.std())


def _sv_stats_pil(image):
    rgb = image.convert("RGB")
    pixel_data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
    pixels = list(pixel_data)
    if not pixels:
        return 0.0, 0.0, 0.0, 0.0

    s_sum = s_sq_sum = v_sum = v_sq_sum = 0.0
    for red, green, blue in pixels:
        _, s_cv, v_cv = _pixel_hsv_cv(red, green, blue)
        s_sum += s_cv
        s_sq_sum += s_cv * s_cv
        v_sum += v_cv
        v_sq_sum += v_cv * v_cv

    total = len(pixels)
    s_mean = s_sum / total
    v_mean = v_sum / total
    s_std = max(s_sq_sum / total - s_mean * s_mean, 0.0) ** 0.5
    v_std = max(v_sq_sum / total - v_mean * v_mean, 0.0) ** 0.5
    return s_mean, s_std, v_mean, v_std


def _crop_fraction(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Crop a fractional (x_off, y_off, w, h) sub-region, clamped to >=1px."""
    width, height = image.size
    x_off, y_off, w_frac, h_frac = box
    left = min(max(int(width * x_off), 0), width - 1)
    top = min(max(int(height * y_off), 0), height - 1)
    right = min(width, max(left + 1, left + int(width * w_frac)))
    bottom = min(height, max(top + 1, top + int(height * h_frac)))
    return image.crop((left, top, right, bottom))


# ===========================================================================
# 黄色羁绊条 (bond bar)
# ===========================================================================


def bond_yellow_ratio(image: Image.Image) -> float:
    """Yellow coverage (0.0-1.0) of a bond-bar crop, after 3x3 dilation.

    输入: 单张卡位的羁绊进度条裁剪图 (卡位内大约 x 10%-90%, y 82%-90%,
    见 CARD_BOND_BAR_BOX)。占比含 3x3 膨胀, 与源 _detect_yellow_bar 一致。
    """
    try:
        ratio, _ = _mask_stats(
            image, BOND_YELLOW_HSV_LOWER, BOND_YELLOW_HSV_UPPER, dilate=True
        )
        return ratio
    except Exception as e:
        logger.debug(f"[bond_yellow_ratio] pixel analysis failed: {e}")
        return 0.0


def is_bond_yellow(image: Image.Image) -> bool:
    """True when the bond bar crop is yellow enough (高羁绊, ratio >= 0.35)."""
    return bond_yellow_ratio(image) >= BOND_YELLOW_RATIO


# ===========================================================================
# 图标存在性 / 计数
# ===========================================================================


def has_card_icon(image: Image.Image) -> bool:
    """Whether a small patch contains a support-card icon (S/V statistics).

    输入: 单个图标槽附近的小块裁剪图 (几像素见方即可)。
    判定 = 彩色图标 或 灰色/高亮立绘 (阈值见 ICON_* 常量, 源 icon_counter.py)。
    """
    try:
        s_mean, s_std, v_mean, v_std = _sv_stats(image)
    except Exception as e:
        logger.debug(f"[has_card_icon] pixel analysis failed: {e}")
        return False

    color_icon = (
        s_mean > ICON_COLOR_SAT_MEAN_MIN
        and v_mean > ICON_COLOR_VAL_MEAN_MIN
        and s_std > ICON_COLOR_SAT_STD_MIN
    )
    if color_icon:
        if s_mean < ICON_COLOR_SAT_MEAN_SPLIT:
            color_icon = s_std > ICON_COLOR_SAT_STD_LOW_MIN
        else:
            color_icon = s_std > ICON_COLOR_SAT_STD_HIGH_MIN

    gray_icon = v_mean > ICON_GRAY_VAL_MEAN_MIN and v_std > ICON_GRAY_VAL_STD_MIN
    return color_icon or gray_icon


def count_card_icons(
    image: Image.Image,
    *,
    center_x: float = ICON_CENTER_X,
    start_y: float = ICON_START_Y,
    spacing: float = ICON_SPACING,
    max_slots: int = MAX_ICON_SLOTS,
    check_radius: float = ICON_CHECK_RADIUS,
) -> int:
    """Count circular support-card icons down a vertical slot column (0-8).

    输入: 训练选择界面截图 (或保持相同相对布局的裁剪图)。默认几何沿用源
    icon_counter.py: 图标列 x≈73%, 自 y≈13% 每 8% 一槽。逐槽自上而下取
    (2*check_radius*宽) 见方的小块做 has_card_icon 判定, 在第一个空槽停止
    (与源 count_circular_icons 行为一致)。
    """
    try:
        width, height = image.size
        check = max(1, int(width * check_radius))
        count = 0
        for slot in range(max_slots):
            cx = int(width * center_x)
            cy = int(height * (start_y + slot * spacing))
            left = max(0, cx - check)
            top = max(0, cy - check)
            right = min(width, cx + check)
            bottom = min(height, cy + check)
            if right <= left or bottom <= top:
                break
            if has_card_icon(image.crop((left, top, right, bottom))):
                count += 1
            else:
                break
        return count
    except Exception as e:
        logger.debug(f"[count_card_icons] icon counting failed: {e}")
        return 0


def apply_icon_priority(counts: Sequence[int], build_direction: str = "attack") -> int:
    """Pick the training row index (0-4) from per-row icon counts.

    纯数据规则, 移植自 icon_counter.py apply_priority_rule:
    集中(3)/保护(4) 任一 ≥4 → 二者取大; 否则前三行(力量/体力/韧性)取最多;
    并列按基调: "attack" → 0,1,2 优先, "survival" → 2,1,0 优先。
    counts 需为 5 行的图标数 [力量, 体力, 韧性, 集中, 保护]。
    """
    if counts[3] >= 4 or counts[4] >= 4:
        return 3 if counts[3] >= counts[4] else 4

    best_count = max(counts[0], counts[1], counts[2])
    tied = [i for i in range(3) if counts[i] == best_count]
    if len(tied) == 1:
        return tied[0]

    preference = [0, 1, 2] if build_direction == "attack" else [2, 1, 0]
    for idx in preference:
        if idx in tied:
            return idx
    return tied[0]


# ===========================================================================
# 属性图标颜色分类
# ===========================================================================


def classify_attribute_icon(image: Image.Image) -> int | None:
    """Classify a card's top-left attribute icon by dominant HSV color.

    输入: 卡位左上角图标裁剪图 (卡位内大约 x 5%-35%, y 2%-20%, 见
    CARD_ICON_BOX)。返回属性ID 1-5 (1力量/2生命/3韧性/4命中/5保护) 或 None。
    评分 = 占比 * (1 + min(命中像素饱和度均值/255, 0.5)), 占比需 > 0.03;
    力量(红)的 H 额外接受 wrap-around 区间 [160, 180]。源: arcanum.py
    _detect_icon_by_color。
    """
    try:
        best_id: int | None = None
        best_score = 0.0
        for attr_id, (lower, upper) in ATTRIBUTE_ICON_HSV.items():
            wrap = RED_WRAP_HUE if attr_id == STRENGTH_ATTRIBUTE_ID else None
            ratio, mean_masked_s = _mask_stats(image, lower, upper, red_wrap_hue=wrap)
            if ratio > ATTRIBUTE_ICON_RATIO_MIN:
                score = ratio * (1.0 + min(mean_masked_s / 255.0, 0.5))
                if score > best_score:
                    best_score = score
                    best_id = attr_id
        return best_id
    except Exception as e:
        logger.debug(f"[classify_attribute_icon] pixel analysis failed: {e}")
        return None


# ===========================================================================
# 闪光(flash)训练检测
# ===========================================================================


def is_flash_training(image: Image.Image) -> bool:
    """Whether one training-button crop looks like a flash (闪光) button.

    输入: 单个训练按钮的裁剪图 (源项目取按钮中心附近 宽10% x 高5% 的区域)。
    仅运行方法1 (浅黄像素占比 > 0.03); 跨行饱和度对比的方法2 需要整组按钮,
    见 detect_flash_rows。
    """
    try:
        ratio, _ = _mask_stats(image, FLASH_HSV_LOWER, FLASH_HSV_UPPER)
        return ratio > FLASH_RATIO_MIN
    except Exception as e:
        logger.debug(f"[is_flash_training] pixel analysis failed: {e}")
        return False


def detect_flash_rows(images: Sequence[Image.Image]) -> list[bool]:
    """Flash flags for a group of training-button crops (双重检测取并集).

    输入: 同一画面上各训练行按钮的裁剪图列表 (源项目为 5 行)。
    方法1: 每张图独立判浅黄占比 > 0.03; 方法2: 某行饱和度均值显著高于
    全体均值 (> 均值+8 且 > 50) 也判闪光。与源 _detect_flash_training 一致。
    """
    flags: list[bool] = []
    s_means: list[float] = []
    for image in images:
        try:
            ratio, _ = _mask_stats(image, FLASH_HSV_LOWER, FLASH_HSV_UPPER)
            s_mean = _sv_stats(image)[0]
        except Exception as e:
            logger.debug(f"[detect_flash_rows] pixel analysis failed: {e}")
            ratio, s_mean = 0.0, 0.0
        flags.append(ratio > FLASH_RATIO_MIN)
        s_means.append(s_mean)

    if s_means:
        overall_mean = sum(s_means) / len(s_means)
        for i, s_mean in enumerate(s_means):
            if flags[i]:
                continue
            if s_mean > overall_mean + FLASH_SAT_DELTA and s_mean > FLASH_SAT_MIN:
                flags[i] = True
    return flags


# ===========================================================================
# Composite per-card analysis
# ===========================================================================


def analyze_support_card(
    card_image: Image.Image, button_image: Image.Image | None = None
) -> SupportCardSignal:
    """Extract all visual signals from one support-card slot crop.

    输入: card_image = 单张支援卡卡位的完整裁剪图; 模块按 arcanum.py 的默认
    布局比例在其内部取左上角图标区 (CARD_ICON_BOX) 与下方羁绊条区
    (CARD_BOND_BAR_BOX)。button_image = 该卡对应训练按钮的裁剪图(可选);
    闪光是按钮的属性而非卡位的属性, 不提供时 is_flash 恒为 False。
    """
    try:
        bond_crop = _crop_fraction(card_image, CARD_BOND_BAR_BOX)
        icon_crop = _crop_fraction(card_image, CARD_ICON_BOX)
        ratio = bond_yellow_ratio(bond_crop)
        return SupportCardSignal(
            bond_ratio=ratio,
            bond_yellow=ratio >= BOND_YELLOW_RATIO,
            has_icon=has_card_icon(icon_crop),
            is_flash=is_flash_training(button_image) if button_image is not None else False,
        )
    except Exception as e:
        logger.debug(f"[analyze_support_card] analysis failed: {e}")
        return SupportCardSignal(bond_ratio=0.0, bond_yellow=False, has_icon=False, is_flash=False)
