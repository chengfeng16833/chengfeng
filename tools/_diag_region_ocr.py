# -*- coding: utf-8 -*-
"""临时诊断: 对指定图片的指定区域跑 OCR, 并存放大裁剪图。

用法: python -B tools/_diag_region_ocr.py <图片> <区域名> [x y w h]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from starsavior_trainer.ocr import PaddleOcrEngine  # noqa: E402

img_path, name = sys.argv[1], sys.argv[2]
if len(sys.argv) >= 7:
    x, y, w, h = (int(v) for v in sys.argv[3:7])
else:
    from starsavior_trainer.regions import load_region_profile

    rect = load_region_profile("config/regions/2560x1440.json").regions[name]
    x, y, w, h = rect.x, rect.y, rect.width, rect.height

img = Image.open(img_path)
crop = img.crop((x, y, x + w, y + h))
out = Path("debug/prejourney_calib") / f"ocr_{name}.png"
out.parent.mkdir(parents=True, exist_ok=True)
crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS).save(out)

ocr = PaddleOcrEngine()
result = ocr.read_text(crop)
print(f"region={name} box=({x},{y},{w},{h})")
print(f"OCR: '{result.text}' confidence={result.confidence:.2f}")
print(f"crop saved -> {out}")
