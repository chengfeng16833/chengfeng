# -*- coding: utf-8 -*-
"""像素指纹分类(fingerprint.py + classify_hybrid 指纹快路径)的单元测试。

全部用注入的假指纹 + 合成纯色图, 不依赖 config/fingerprints/ 真库 —
真库的回归由 tools/_mine_fingerprints.py 全库自检负责(误判=0 才写盘)。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from starsavior_trainer.classifier import classify_hybrid
from starsavior_trainer.fingerprint import (
    BASE_SIZE,
    FingerprintPoint,
    ScreenFingerprint,
    load_fingerprints,
    match_fingerprint,
)
from starsavior_trainer.models import Screen
from starsavior_trainer.ocr import OcrResult
from starsavior_trainer.regions import load_region_profile


def _fp(screen: Screen, rgb: tuple[int, int, int], tol: int = 8) -> ScreenFingerprint:
    points = tuple(
        FingerprintPoint(x=200 + i * 300, y=200 + i * 120, rgb=rgb, tol=tol)
        for i in range(8)
    )
    return ScreenFingerprint(screen=screen, points=points)


class _BoomOcr:
    """指纹直接命中的画面不应触发任何 OCR — 触发即测试失败。"""

    def read_text(self, _image: Image.Image) -> OcrResult:
        raise AssertionError("指纹命中时不应触发 OCR")


class _FixedTextOcr:
    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self, _image: Image.Image) -> OcrResult:
        return OcrResult(text=self._text, confidence=0.95)


class FingerprintPointTests(unittest.TestCase):
    def test_matches_within_and_outside_tolerance(self) -> None:
        point = FingerprintPoint(x=0, y=0, rgb=(100, 100, 100), tol=10)
        self.assertTrue(point.matches((100, 100, 100)))
        self.assertTrue(point.matches((110, 90, 105)))  # 恰好在容差边界
        self.assertFalse(point.matches((111, 100, 100)))  # 单通道超 1
        self.assertFalse(point.matches((100, 100, 89)))


class MatchFingerprintTests(unittest.TestCase):
    def test_unique_full_hit_wins(self) -> None:
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        fps = {
            Screen.SHOP: _fp(Screen.SHOP, (10, 20, 30)),
            Screen.TRAINING_HUB: _fp(Screen.TRAINING_HUB, (200, 50, 50)),
        }
        self.assertEqual(match_fingerprint(image, fps), Screen.SHOP)

    def test_single_point_miss_abstains(self) -> None:
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        fps = {Screen.SHOP: _fp(Screen.SHOP, (10, 20, 80))}  # 蓝通道差 50 > tol
        self.assertIsNone(match_fingerprint(image, fps))

    def test_two_full_hits_abstain(self) -> None:
        # 两个画面指纹同时全命中 → 区分度不足, 必须弃权交给 OCR。
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        fps = {
            Screen.SHOP: _fp(Screen.SHOP, (10, 20, 30)),
            Screen.BATTLE: _fp(Screen.BATTLE, (10, 20, 30)),
        }
        self.assertIsNone(match_fingerprint(image, fps))

    def test_16_9_frame_is_scaled(self) -> None:
        # 1280x720 帧: 指纹坐标按 2560x1440 标定, 应等比缩放后采样。
        image = Image.new("RGB", (1280, 720), (10, 20, 30))
        fps = {Screen.SHOP: _fp(Screen.SHOP, (10, 20, 30))}
        self.assertEqual(match_fingerprint(image, fps), Screen.SHOP)

    def test_non_16_9_frame_abstains(self) -> None:
        image = Image.new("RGB", (1280, 1024), (10, 20, 30))
        fps = {Screen.SHOP: _fp(Screen.SHOP, (10, 20, 30))}
        self.assertIsNone(match_fingerprint(image, fps))

    def test_empty_fingerprints_abstain(self) -> None:
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        self.assertIsNone(match_fingerprint(image, {}))


class LoadFingerprintsTests(unittest.TestCase):
    def test_roundtrip_and_unknown_screen_skipped(self) -> None:
        payload = {
            "screens": {
                "shop": {
                    "points": [{"x": 12, "y": 34, "rgb": [1, 2, 3], "tol": 9}],
                },
                "no_such_screen_xyz": {
                    "points": [{"x": 1, "y": 1, "rgb": [0, 0, 0], "tol": 8}],
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fp.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_fingerprints(path)
        self.assertEqual(set(loaded), {Screen.SHOP})
        point = loaded[Screen.SHOP].points[0]
        self.assertEqual((point.x, point.y, point.rgb, point.tol), (12, 34, (1, 2, 3), 9))


class ClassifyHybridFingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_region_profile("config/regions/2560x1440.json")

    def test_fingerprint_hit_returns_without_any_ocr(self) -> None:
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        fps = {Screen.SHOP: _fp(Screen.SHOP, (10, 20, 30))}
        observation = classify_hybrid(image, self.profile, _BoomOcr(), fingerprints=fps)
        self.assertEqual(observation.screen, Screen.SHOP)
        self.assertEqual(observation.source, "fingerprint")
        self.assertGreaterEqual(observation.confidence, 0.95)

    def test_event_choice_hit_with_real_options_stays_event_choice(self) -> None:
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        fps = {Screen.EVENT_CHOICE: _fp(Screen.EVENT_CHOICE, (10, 20, 30))}
        observation = classify_hybrid(
            image, self.profile, _FixedTextOcr("提升力量"), fingerprints=fps
        )
        self.assertEqual(observation.screen, Screen.EVENT_CHOICE)

    def test_event_choice_hit_without_options_downgrades_to_dialogue(self) -> None:
        # 指纹层面 dialogue 与 event_choice 同脸 — 选项行无字时必须降级为对话,
        # 否则 policy 找不到选项会 pause(实跑"卡在过场"老症状)。
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        fps = {Screen.EVENT_CHOICE: _fp(Screen.EVENT_CHOICE, (10, 20, 30))}
        observation = classify_hybrid(
            image, self.profile, _FixedTextOcr(""), fingerprints=fps
        )
        self.assertEqual(observation.screen, Screen.DIALOGUE)
        self.assertEqual(observation.source, "fingerprint")

    def test_explicit_empty_fingerprints_disable_fast_path(self) -> None:
        # fingerprints={} 是看门狗复核的"换一双眼睛"开关 — 必须真走 OCR 老路。
        image = Image.new("RGB", BASE_SIZE, (10, 20, 30))
        observation = classify_hybrid(
            image, self.profile, _FixedTextOcr(""), fingerprints={}
        )
        self.assertNotEqual(observation.source, "fingerprint")


if __name__ == "__main__":
    unittest.main()
