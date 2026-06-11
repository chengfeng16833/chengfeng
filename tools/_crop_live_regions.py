# -*- coding: utf-8 -*-
"""临时诊断: 从实机帧裁出候选区域放大保存, 用于人工定坐标。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

src_path = sys.argv[1] if len(sys.argv) > 1 else "screenshots/prejourney_live_003.png"
src = Image.open(src_path)
out_dir = Path("debug/prejourney_calib")
out_dir.mkdir(parents=True, exist_ok=True)

# 菜单面板第一行(付费商店..旅程)附近
crops = {
    "panel_row1": (1300, 250, 2200, 520),
}
for name, box in crops.items():
    img = src.crop(box)
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    path = out_dir / f"{name}.png"
    img.save(path)
    print(name, "box=", box, "->", path)
