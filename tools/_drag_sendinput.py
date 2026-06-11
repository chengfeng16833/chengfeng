# -*- coding: utf-8 -*-
"""临时诊断: SendInput 级拖拽(绝对坐标 MOVE 序列), 先点弹窗空白处激活窗口。

用法: python -B tools/_drag_sendinput.py <x1> <y1> <x2> <y2>
"""
import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starsavior_trainer.capture import find_window  # noqa: E402

user32 = ctypes.windll.user32
SM_CXSCREEN, SM_CYSCREEN = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


SW, SH = user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)


def send_mouse(flags: int, sx: int = 0, sy: int = 0) -> None:
    inp = INPUT(type=0)
    if flags & MOUSEEVENTF_ABSOLUTE:
        inp.mi = MOUSEINPUT(int(sx * 65535 / SW), int(sy * 65535 / SH), 0, flags, 0, None)
    else:
        inp.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


x1, y1, x2, y2 = (int(v) for v in sys.argv[1:5])
info = find_window("starsavior")
if info is None or info.title.strip().lower() != "starsavior":
    print("没找到 StarSavior 游戏窗口")
    sys.exit(1)
ox, oy = info.rect.x, info.rect.y

# 先把窗口带到前台(激活点: 弹窗标题附近空白, 客户区 (700, 290))
send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, ox + 700, oy + 290)
time.sleep(0.1)
send_mouse(MOUSEEVENTF_LEFTDOWN)
time.sleep(0.05)
send_mouse(MOUSEEVENTF_LEFTUP)
time.sleep(0.4)

# SendInput 拖拽: 按住-停顿-分步移动-停稳-松开
send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, ox + x1, oy + y1)
time.sleep(0.15)
send_mouse(MOUSEEVENTF_LEFTDOWN)
time.sleep(0.3)
steps = 20
for i in range(1, steps + 1):
    nx = ox + x1 + (x2 - x1) * i // steps
    ny = oy + y1 + (y2 - y1) * i // steps
    send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny)
    time.sleep(0.025)
time.sleep(0.25)
send_mouse(MOUSEEVENTF_LEFTUP)
print(f"sendinput-dragged client ({x1},{y1}) -> ({x2},{y2})")
