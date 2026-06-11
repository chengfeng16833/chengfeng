"""Tests for support-card (阿尔克那) visual detection.

All images are synthesized with PIL (solid blocks / checker patterns) so the
suite runs without any real game screenshots.
"""

import unittest

from PIL import Image

from starsavior_trainer import support_cards
from starsavior_trainer.support_cards import (
    BOND_YELLOW_RATIO,
    ICON_CENTER_X,
    ICON_CHECK_RADIUS,
    ICON_SPACING,
    ICON_START_Y,
    SupportCardSignal,
    analyze_support_card,
    apply_icon_priority,
    bond_yellow_ratio,
    classify_attribute_icon,
    count_card_icons,
    detect_flash_rows,
    has_card_icon,
    is_bond_yellow,
    is_flash_training,
)

# 合成测试用色 (HSV 注释为 OpenCV 单位: H<180, S/V<=255)
YELLOW = (255, 200, 40)  # H≈22, S≈215, V=255 → 在羁绊黄范围 [18-38, 80+, 100+]
AMBER = (255, 230, 170)  # H≈21, S≈85, V=255 → 在闪光浅黄范围 [12-45, 35+, 130+]
GRAY = (60, 60, 60)  # S=0 → 任何彩色范围都不命中
DARK = (40, 40, 40)
BLUE_GRAY = (90, 110, 140)  # H≈108 → 非闪光的普通按钮色
SAT_BLUE = (60, 80, 200)  # S≈178 → 触发闪光方法2 (相对饱和度), 但非浅黄
RED = (220, 30, 30)  # H≈0 → 属性1 力量
GREEN = (60, 180, 60)  # H≈60 → 属性3 韧性
BLUE_ICON = (40, 80, 190)  # H≈112 → 属性4 命中
WHITE = (250, 250, 250)


def _solid(color, size=(60, 20)):
    return Image.new("RGB", size, color)


def _checker(size, color_a, color_b, step=2):
    """两色棋盘格: 饱和度/明度方差大, 用来模拟彩色图标块。"""
    image = Image.new("RGB", size, color_a)
    for y in range(size[1]):
        for x in range(size[0]):
            if ((x // step) + (y // step)) % 2:
                image.putpixel((x, y), color_b)
    return image


class BondBarTest(unittest.TestCase):
    def test_full_yellow_bar_is_high_bond(self):
        bar = _solid(YELLOW, (80, 10))
        self.assertGreaterEqual(bond_yellow_ratio(bar), 0.99)
        self.assertTrue(is_bond_yellow(bar))

    def test_partial_yellow_bar_ratio_and_threshold(self):
        # 100x10 灰底, 左侧 40 列黄色 → 原始占比 0.40, 3x3 膨胀后 ≈ 0.41。
        bar = _solid(GRAY, (100, 10))
        bar.paste(YELLOW, (0, 0, 40, 10))
        ratio = bond_yellow_ratio(bar)
        self.assertAlmostEqual(ratio, 0.41, delta=0.02)
        self.assertTrue(is_bond_yellow(bar))

    def test_low_fill_bar_not_yellow(self):
        # 仅 20 列黄色 → 膨胀后 ≈ 0.21 < 0.35。
        bar = _solid(GRAY, (100, 10))
        bar.paste(YELLOW, (0, 0, 20, 10))
        self.assertLess(bond_yellow_ratio(bar), BOND_YELLOW_RATIO)
        self.assertFalse(is_bond_yellow(bar))

    def test_gray_bar_not_yellow(self):
        bar = _solid(GRAY, (80, 10))
        self.assertEqual(bond_yellow_ratio(bar), 0.0)
        self.assertFalse(is_bond_yellow(bar))

    def test_blue_bar_not_yellow(self):
        self.assertFalse(is_bond_yellow(_solid(SAT_BLUE, (80, 10))))


class FlashDetectionTest(unittest.TestCase):
    def test_amber_button_is_flash(self):
        self.assertTrue(is_flash_training(_solid(AMBER, (40, 16))))

    def test_muted_button_not_flash(self):
        self.assertFalse(is_flash_training(_solid(BLUE_GRAY, (40, 16))))

    def test_flash_rows_method1_light_yellow(self):
        rows = [
            _solid(BLUE_GRAY, (40, 16)),
            _solid(AMBER, (40, 16)),
            _solid(BLUE_GRAY, (40, 16)),
            _solid(BLUE_GRAY, (40, 16)),
            _solid(BLUE_GRAY, (40, 16)),
        ]
        self.assertEqual(detect_flash_rows(rows), [False, True, False, False, False])

    def test_flash_rows_method2_relative_saturation(self):
        # 饱和蓝不在浅黄范围 (方法1不命中), 但饱和度显著高于其余行 → 方法2命中。
        rows = [_solid(SAT_BLUE, (40, 16))] + [_solid(GRAY, (40, 16)) for _ in range(4)]
        self.assertEqual(detect_flash_rows(rows), [True, False, False, False, False])

    def test_flash_rows_empty_input(self):
        self.assertEqual(detect_flash_rows([]), [])

    def test_flash_rows_all_black(self):
        rows = [_solid((0, 0, 0), (40, 16)) for _ in range(5)]
        self.assertEqual(detect_flash_rows(rows), [False] * 5)


class IconDetectionTest(unittest.TestCase):
    def test_colorful_patch_has_icon(self):
        # 红白棋盘格: 饱和度均值高 + 方差大 → 彩色图标。
        self.assertTrue(has_card_icon(_checker((20, 20), RED, WHITE)))

    def test_bright_contrast_gray_patch_has_icon(self):
        # 亮/暗灰棋盘格: 无饱和度, 但明度均值高 + 方差大 → 灰色/高亮立绘图标。
        self.assertTrue(has_card_icon(_checker((20, 20), WHITE, (100, 100, 100))))

    def test_flat_gray_patch_no_icon(self):
        self.assertFalse(has_card_icon(_solid((90, 90, 90), (20, 20))))

    def test_black_patch_no_icon(self):
        self.assertFalse(has_card_icon(_solid((0, 0, 0), (20, 20))))

    def _paint_slot(self, image, slot):
        width, height = image.size
        cx = int(width * ICON_CENTER_X)
        cy = int(height * (ICON_START_Y + slot * ICON_SPACING))
        patch = _checker((14, 14), RED, WHITE)
        image.paste(patch, (cx - 7, cy - 7))

    def test_count_three_contiguous_icons(self):
        image = _solid(DARK, (200, 300))
        for slot in range(3):
            self._paint_slot(image, slot)
        self.assertEqual(count_card_icons(image), 3)

    def test_count_stops_at_first_empty_slot(self):
        image = _solid(DARK, (200, 300))
        self._paint_slot(image, 0)
        self._paint_slot(image, 2)  # 槽1为空 → 在槽1停止计数
        self.assertEqual(count_card_icons(image), 1)

    def test_count_zero_on_empty_column(self):
        self.assertEqual(count_card_icons(_solid(DARK, (200, 300))), 0)

    def test_count_check_radius_floor_on_small_image(self):
        # 极小图: check 半径取整后落到 max(1, ...) 分支, 不应崩溃。
        self.assertEqual(max(1, int(10 * ICON_CHECK_RADIUS)), 1)
        self.assertEqual(count_card_icons(_solid(DARK, (10, 10))), 0)


class AttributeIconTest(unittest.TestCase):
    def test_red_icon_is_strength(self):
        self.assertEqual(classify_attribute_icon(_solid(RED, (16, 16))), 1)

    def test_green_icon_is_toughness(self):
        self.assertEqual(classify_attribute_icon(_solid(GREEN, (16, 16))), 3)

    def test_blue_icon_is_accuracy(self):
        self.assertEqual(classify_attribute_icon(_solid(BLUE_ICON, (16, 16))), 4)

    def test_gray_icon_unclassified(self):
        self.assertIsNone(classify_attribute_icon(_solid((128, 128, 128), (16, 16))))


class IconPriorityTest(unittest.TestCase):
    def test_focus_rule_when_focus_high(self):
        self.assertEqual(apply_icon_priority([0, 0, 0, 4, 2]), 3)

    def test_protect_rule_when_protect_higher(self):
        self.assertEqual(apply_icon_priority([0, 0, 0, 4, 5]), 4)

    def test_front_three_max_wins(self):
        self.assertEqual(apply_icon_priority([3, 1, 2, 0, 0]), 0)

    def test_tie_breaks_by_attack_preference(self):
        self.assertEqual(apply_icon_priority([2, 2, 1, 0, 0], "attack"), 0)

    def test_tie_breaks_by_survival_preference(self):
        self.assertEqual(apply_icon_priority([2, 2, 2, 0, 0], "survival"), 2)


class AnalyzeSupportCardTest(unittest.TestCase):
    def _make_card(self, *, with_bond=True, with_icon=True):
        # 100x100 卡位: 图标区 = (5,2,35,20), 羁绊条区 = (10,82,90,90)。
        card = _solid((120, 120, 120), (100, 100))
        if with_icon:
            card.paste(_checker((30, 18), RED, WHITE), (5, 2))
        if with_bond:
            card.paste(YELLOW, (10, 82, 90, 90))
        return card

    def test_card_with_yellow_bond_and_icon(self):
        signal = analyze_support_card(self._make_card())
        self.assertIsInstance(signal, SupportCardSignal)
        self.assertGreaterEqual(signal.bond_ratio, 0.99)
        self.assertTrue(signal.bond_yellow)
        self.assertTrue(signal.has_icon)
        self.assertFalse(signal.is_flash)  # 未提供按钮裁剪图 → 恒 False

    def test_plain_card_all_negative(self):
        signal = analyze_support_card(_solid((120, 120, 120), (100, 100)))
        self.assertEqual(signal.bond_ratio, 0.0)
        self.assertFalse(signal.bond_yellow)
        self.assertFalse(signal.has_icon)
        self.assertFalse(signal.is_flash)

    def test_flash_comes_from_button_image(self):
        card = self._make_card()
        flash_signal = analyze_support_card(card, button_image=_solid(AMBER, (40, 16)))
        muted_signal = analyze_support_card(card, button_image=_solid(BLUE_GRAY, (40, 16)))
        self.assertTrue(flash_signal.is_flash)
        self.assertFalse(muted_signal.is_flash)

    def test_partial_bond_keeps_ratio_below_threshold(self):
        card = self._make_card(with_bond=False)
        card.paste(YELLOW, (10, 82, 26, 90))  # 羁绊条仅填 20% → 不应判高羁绊
        signal = analyze_support_card(card)
        self.assertGreater(signal.bond_ratio, 0.0)
        self.assertFalse(signal.bond_yellow)


class EdgeCaseTest(unittest.TestCase):
    def test_one_pixel_black_image_is_safe(self):
        image = Image.new("RGB", (1, 1), (0, 0, 0))
        self.assertEqual(bond_yellow_ratio(image), 0.0)
        self.assertFalse(is_bond_yellow(image))
        self.assertFalse(has_card_icon(image))
        self.assertFalse(is_flash_training(image))
        self.assertIsNone(classify_attribute_icon(image))
        self.assertEqual(count_card_icons(image), 0)
        signal = analyze_support_card(image)
        self.assertEqual(
            signal,
            SupportCardSignal(bond_ratio=0.0, bond_yellow=False, has_icon=False, is_flash=False),
        )

    def test_tiny_image_is_safe(self):
        image = Image.new("RGB", (2, 2), (10, 10, 10))
        self.assertEqual(bond_yellow_ratio(image), 0.0)
        self.assertFalse(has_card_icon(image))
        self.assertEqual(count_card_icons(image), 0)
        self.assertFalse(analyze_support_card(image).bond_yellow)

    def test_black_image_all_negative(self):
        image = Image.new("RGB", (50, 50), (0, 0, 0))
        self.assertFalse(is_bond_yellow(image))
        self.assertFalse(is_flash_training(image))
        self.assertFalse(has_card_icon(image))
        self.assertIsNone(classify_attribute_icon(image))
        self.assertEqual(count_card_icons(image), 0)


class PilFallbackTest(unittest.TestCase):
    """强制走纯 PIL 像素遍历路径 (模拟 numpy 不可用), 复核核心检测。"""

    def setUp(self):
        self._saved_flag = support_cards._NUMPY_IMPORT_FAILED
        support_cards._NUMPY_IMPORT_FAILED = True

    def tearDown(self):
        support_cards._NUMPY_IMPORT_FAILED = self._saved_flag

    def test_pil_path_core_detections(self):
        self.assertTrue(is_bond_yellow(_solid(YELLOW, (40, 8))))
        self.assertFalse(is_bond_yellow(_solid(GRAY, (40, 8))))
        self.assertTrue(is_flash_training(_solid(AMBER, (40, 16))))
        self.assertFalse(is_flash_training(_solid(BLUE_GRAY, (40, 16))))
        self.assertTrue(has_card_icon(_checker((20, 20), RED, WHITE)))
        self.assertFalse(has_card_icon(_solid((90, 90, 90), (20, 20))))
        self.assertEqual(classify_attribute_icon(_solid(RED, (16, 16))), 1)

    def test_pil_path_partial_bar_with_dilation(self):
        bar = _solid(GRAY, (60, 10))
        bar.paste(YELLOW, (0, 0, 24, 10))  # 24/60 列黄 → 膨胀后 25/60 ≈ 0.4167
        self.assertAlmostEqual(bond_yellow_ratio(bar), 25 / 60, delta=0.02)

    def test_pil_path_handles_one_pixel_image(self):
        image = Image.new("RGB", (1, 1), (0, 0, 0))
        self.assertEqual(bond_yellow_ratio(image), 0.0)
        self.assertFalse(has_card_icon(image))
        self.assertIsNone(classify_attribute_icon(image))


class NumpyPilParityTest(unittest.TestCase):
    def test_bond_ratio_matches_between_paths(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not available; PIL path already covered above")

        bar = _solid(GRAY, (60, 10))
        bar.paste(YELLOW, (0, 0, 24, 10))
        saved = support_cards._NUMPY_IMPORT_FAILED
        try:
            support_cards._NUMPY_IMPORT_FAILED = False
            numpy_ratio = bond_yellow_ratio(bar)
            support_cards._NUMPY_IMPORT_FAILED = True
            pil_ratio = bond_yellow_ratio(bar)
        finally:
            support_cards._NUMPY_IMPORT_FAILED = saved
        self.assertAlmostEqual(numpy_ratio, pil_ratio, delta=0.01)


if __name__ == "__main__":
    unittest.main()
