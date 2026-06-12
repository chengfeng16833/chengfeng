# -*- coding: utf-8 -*-
"""临时诊断: WinRT vs Paddle vs Hybrid 在真帧上的速度与中文质量对比。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from starsavior_trainer.ocr import PaddleOcrEngine, WinRtOcrEngine, create_hybrid_ocr_engine  # noqa: E402

frame = Image.open(sys.argv[1] if len(sys.argv) > 1 else "screenshots/prejourney_live_001.png")
# 三个有代表性的区域: 中文菜单列 / 小号数字混排 / 标题
crops = {
    "菜单列(中文竖排)": frame.crop((150, 420, 370, 1080)),
    "顶部标题(旅程起点)": frame.crop((180, 20, 420, 80)),
    "数值(能力值祝福)": frame.crop((1303, 173, 1627, 220)),
}

engines = {}
try:
    t0 = time.perf_counter()
    engines["winrt"] = WinRtOcrEngine()
    print(f"WinRT 引擎可用 (init {time.perf_counter()-t0:.2f}s)")
except Exception as exc:
    print(f"WinRT 不可用: {exc}")
t0 = time.perf_counter()
engines["paddle"] = PaddleOcrEngine()
print(f"Paddle 引擎 init {time.perf_counter()-t0:.2f}s")

for name, crop in crops.items():
    print(f"\n--- {name} ({crop.width}x{crop.height}) ---")
    for label, engine in engines.items():
        t0 = time.perf_counter()
        result = engine.read_text(crop)
        dt = time.perf_counter() - t0
        # 第二次读, 排除首次热身
        t1 = time.perf_counter()
        engine.read_text(crop)
        dt2 = time.perf_counter() - t1
        print(f"  {label:7s} {dt:.3f}s/{dt2:.3f}s conf={result.confidence:.2f} text='{result.text.strip()[:40]}'")
