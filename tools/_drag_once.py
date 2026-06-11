# -*- coding: utf-8 -*-
"""临时诊断: 在游戏窗口客户区从 A 滑动到 B(手游式: 按住-停顿-分步移动-松开)。

用法: python -B tools/_drag_once.py <x1> <y1> <x2> <y2>
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyautogui  # noqa: E402

from starsavior_trainer.capture import find_window  # noqa: E402

x1, y1, x2, y2 = (int(v) for v in sys.argv[1:5])
info = find_window("starsavior")
if info is None or info.title.strip().lower() != "starsavior":
    print("没找到 StarSavior 游戏窗口")
    sys.exit(1)
ox, oy = info.rect.x, info.rect.y
before = pyautogui.position()

pyautogui.moveTo(ox + x1, oy + y1)
time.sleep(0.15)
pyautogui.mouseDown(button="left")
time.sleep(0.25)  # 按住停顿, 让游戏识别为拖拽起手而非点击
steps = 12
for i in range(1, steps + 1):
    nx = ox + x1 + (x2 - x1) * i // steps
    ny = oy + y1 + (y2 - y1) * i // steps
    pyautogui.moveTo(nx, ny)
    time.sleep(0.03)
time.sleep(0.15)  # 停稳再松, 避免惯性回弹
pyautogui.mouseUp(button="left")
time.sleep(0.1)
pyautogui.moveTo(before.x, before.y)
print(f"slow-dragged client ({x1},{y1}) -> ({x2},{y2})")
