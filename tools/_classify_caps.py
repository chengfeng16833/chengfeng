"""把采集的 61 张截图用现有分类器过一遍，按画面分组，便于挑代表帧裁模板。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PIL import Image

from starsavior_trainer.classifier import classify_hybrid
from starsavior_trainer.ocr import PaddleOcrEngine
from starsavior_trainer.regions import load_region_profile, scale_region_profile

ocr = PaddleOcrEngine()
base = load_region_profile("config/regions/2560x1440.json")

groups: dict[str, list[str]] = defaultdict(list)
for p in sorted(Path("screenshots/capture").glob("*.png")):
    img = Image.open(p).convert("RGB")
    profile = scale_region_profile(base, img.size)
    obs = classify_hybrid(img, profile, ocr)
    groups[f"{obs.screen.value}"].append(f"{p.name}({obs.confidence:.2f})")

print(f"=== 按画面分组 (共 {sum(len(v) for v in groups.values())} 张) ===")
for screen in sorted(groups, key=lambda s: -len(groups[s])):
    print(f"\n[{screen}]  x{len(groups[screen])}")
    for f in groups[screen]:
        print(f"    {f}")
