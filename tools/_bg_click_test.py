# -*- coding: utf-8 -*-
"""后台点击可行性测试: 用 PostMessage 直接给游戏窗口发点击消息(不动鼠标、
不抢前台), 对比点击前后帧哈希判断游戏是否响应。

用法: python -B tools/_bg_click_test.py <客户区x> <客户区y>
"""
import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starsavior_trainer.capture import _capture_client_via_printwindow, find_window  # noqa: E402

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
MK_LBUTTON = 0x0001

user32 = ctypes.windll.user32

cx, cy = int(sys.argv[1]), int(sys.argv[2])
info = find_window("starsavior")
if info is None or info.title.strip().lower() != "starsavior":
    print("没找到 StarSavior 窗口")
    sys.exit(1)
hwnd = info.hwnd

# 找到真正接收输入的子窗口(Unity 通常有 child render window)
point = ctypes.wintypes.POINT(cx, cy) if hasattr(ctypes, "wintypes") else None
child = user32.ChildWindowFromPoint(hwnd, cy << 16 | (cx & 0xFFFF)) if False else 0
targets = [hwnd]
# 枚举子窗口也试一遍
children = []

def _enum_child(child_hwnd, _l):
    children.append(child_hwnd)
    return True

EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumChildWindows(hwnd, EnumChildProc(_enum_child), None)
targets.extend(children)
print(f"窗口 hwnd={hwnd} 子窗口={len(children)} 个")

before = _capture_client_via_printwindow(hwnd)
sig_before = before.convert("L").resize((32, 18)).tobytes() if before else None

lparam = (cy << 16) | (cx & 0xFFFF)
for target in targets:
    user32.PostMessageW(target, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.03)
    user32.PostMessageW(target, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.06)
    user32.PostMessageW(target, WM_LBUTTONUP, 0, lparam)
    time.sleep(0.05)
print(f"已向 {len(targets)} 个目标 PostMessage 点击 client=({cx},{cy})")

time.sleep(1.5)
after = _capture_client_via_printwindow(hwnd)
sig_after = after.convert("L").resize((32, 18)).tobytes() if after else None

if sig_before and sig_after:
    diff = sum(1 for a, b in zip(sig_before, sig_after) if abs(a - b) > 10)
    ratio = diff / len(sig_before)
    print(f"帧变化率: {ratio:.1%} -> {'游戏响应了后台点击 ✓' if ratio > 0.02 else '游戏无响应(忽视后台消息)✗'}")
    after.save("screenshots/bg_click_after.png")
    print("after 帧已存 screenshots/bg_click_after.png")
