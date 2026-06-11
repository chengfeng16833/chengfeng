# -*- coding: utf-8 -*-
"""临时诊断: 从实机主界面帧裁出候选区域放大保存, 用于人工定坐标。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

src = Image.open("screenshots/prejourney_live_001.png")
out_dir = Path("debug/prejourney_calib")
out_dir.mkdir(parents=True, exist_ok=True)

crops = {
    # 右上角整条图标区(找菜单按钮)
    "topright": (2200, 0, 2560, 100),
    # 左侧菜单竖排(战斗..观测)
    "leftmenu": (80, 380, 360, 1120),
}
for name, box in crops.items():
    img = src.crop(box)
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    path = out_dir / f"{name}.png"
    img.save(path)
    print(name, "box=", box, "->", path)
