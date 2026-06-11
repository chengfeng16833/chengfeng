# -*- coding: utf-8 -*-
"""临时诊断: 在游戏窗口客户区坐标处滚动一次(用于弹窗滚动校准)。

用法: python -B tools/_scroll_once.py <客户区x> <客户区y> <clicks(负=向下)>
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyautogui  # noqa: E402

from starsavior_trainer.capture import find_window  # noqa: E402

cx, cy, clicks = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
info = find_window("starsavior")
if info is None or info.title.strip().lower() != "starsavior":
    print("没找到 StarSavior 游戏窗口")
    sys.exit(1)
sx, sy = info.rect.x + cx, info.rect.y + cy
before = pyautogui.position()
pyautogui.moveTo(sx, sy)
time.sleep(0.05)
pyautogui.scroll(clicks * 120)
time.sleep(0.1)
pyautogui.moveTo(before.x, before.y)
print(f"scrolled clicks={clicks} at client=({cx},{cy}) screen=({sx},{sy})")
