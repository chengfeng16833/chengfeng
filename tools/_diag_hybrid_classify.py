# -*- coding: utf-8 -*-
"""临时诊断: 对一帧分别用 信空hybrid(分类用) 和 Paddle 跑分类, 对比结果。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from starsavior_trainer.classifier import classify_hybrid  # noqa: E402
from starsavior_trainer.ocr import HybridOcrEngine, PaddleOcrEngine, create_hybrid_ocr_engine  # noqa: E402
from starsavior_trainer.regions import load_region_profile  # noqa: E402

image = Image.open(sys.argv[1] if len(sys.argv) > 1 else "screenshots/debug_error_004.png")
profile = load_region_profile("config/regions/2560x1440.json")

hybrid = create_hybrid_ocr_engine(verbose=False)
classify_engine = hybrid
if isinstance(hybrid, HybridOcrEngine):
    classify_engine = HybridOcrEngine(
        hybrid.fast_engine, hybrid.detailed_engine,
        fast_min_confidence=hybrid.fast_min_confidence,
        fast_max_area=hybrid.fast_max_area,
        fallback_on_empty=False,
    )

obs1 = classify_hybrid(image, profile, classify_engine)
print(f"信空hybrid: screen={obs1.screen.value} conf={obs1.confidence:.2f}")

paddle = PaddleOcrEngine()
obs2 = classify_hybrid(image, profile, paddle)
print(f"Paddle:    screen={obs2.screen.value} conf={obs2.confidence:.2f}")
