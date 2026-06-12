# -*- coding: utf-8 -*-
"""临时诊断: 对训练画面帧验证选中卡人头计数。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from starsavior_trainer.regions import load_region_profile  # noqa: E402
from starsavior_trainer.screen_reader import _count_training_icons  # noqa: E402

image = Image.open(sys.argv[1] if len(sys.argv) > 1 else "screenshots/live_training_select_latest.png")
profile = load_region_profile("config/regions/2560x1440.json")
count = _count_training_icons(image, profile)
print(f"选中训练的人头数 = {count}")
