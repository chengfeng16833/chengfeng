# -*- coding: utf-8 -*-
"""临时诊断: 对比星标按钮在 开(006)/关(015) 两帧的像素特征, 找检测阈值。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

BOX = (1704, 173, 1704 + 53, 173 + 47)

for name in ("prejourney_live_006.png", "prejourney_live_015.png", "prejourney_live_016.png"):
    img = Image.open(f"screenshots/{name}").convert("RGB").crop(BOX)
    pixels = list(img.getdata())
    n = len(pixels)
    avg = tuple(sum(c[i] for c in pixels) // n for i in range(3))
    # 金黄色占比(星标激活高亮的典型色)
    gold = sum(1 for r, g, b in pixels if r > 180 and g > 130 and b < 140) / n
    # 亮像素占比(白底按钮)
    bright = sum(1 for r, g, b in pixels if r > 200 and g > 200 and b > 200) / n
    print(f"{name}: avg={avg} gold={gold:.2%} bright={bright:.2%}")
    out = Path("debug/prejourney_calib") / f"star_{name}"
    img.resize((img.width * 4, img.height * 4), Image.LANCZOS).save(out)
    print("   saved", out)
