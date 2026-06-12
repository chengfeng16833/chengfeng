# -*- coding: utf-8 -*-
"""临时诊断: 检查旅程起点按钮亮度(蓝=可点, 灰=禁用)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

img = Image.open(sys.argv[1] if len(sys.argv) > 1 else "screenshots/debug_error_013.png").convert("RGB")
# 旅程起点按钮 [1932,1306,535,75] 中心带
box = img.crop((2050, 1320, 2350, 1370))
pixels = list(box.getdata())
n = len(pixels)
blue = sum(1 for r, g, b in pixels if b > 150 and b > r + 40 and b > g + 20) / n
avg = tuple(sum(c[i] for c in pixels) // n for i in range(3))
print(f"journey button avg={avg} blue_ratio={blue:.1%} -> {'ENABLED(blue)' if blue > 0.3 else 'disabled(grey)'}")
