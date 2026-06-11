"""后台自动采集游戏画面(用于做模板库)。

PrintWindow 每秒截一帧(不碰鼠标、不抢焦点)。当画面"稳定"(与上一帧几乎相同)
时自动存一张 —— 过场动画/切换中不存,每个稳定画面只存一张干净图。
存到 screenshots/capture/。手动跑马即可,杀进程停止。
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PIL import ImageChops

from starsavior_trainer.capture import find_window, activate_window, _capture_client_via_printwindow

outdir = Path("screenshots/capture")
outdir.mkdir(parents=True, exist_ok=True)

win = find_window("StarSavior")
if win is None:
    print("WINDOW NOT FOUND")
    raise SystemExit(1)

# 把游戏弹到前台,作为"开始"信号(看到游戏弹出即知采集已开始)
activate_window(win.hwnd)
print(f"已弹出游戏窗口,采集开始: hwnd={win.hwnd}. 手动跑马,画面稳定即自动存.", flush=True)
prev = None
stable_saved = False
n = 0
while True:
    img = _capture_client_via_printwindow(win.hwnd)
    if img is None:
        time.sleep(1.0)
        continue
    if prev is not None:
        diff = float(np.asarray(ImageChops.difference(img.convert("L"), prev.convert("L"))).mean())
        if diff < 6:  # 与上一帧几乎相同 -> 画面稳定
            if not stable_saved:
                n += 1
                name = f"cap_{n:03d}_{time.strftime('%H%M%S')}.png"
                img.save(outdir / name)
                print(f"[{n}] 已存 {name}", flush=True)
                stable_saved = True
        else:  # 画面在变(过场/切换),等它稳定
            stable_saved = False
    prev = img
    time.sleep(1.0)
