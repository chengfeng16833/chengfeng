# -*- coding: utf-8 -*-
"""临时诊断: 按精确窗口标题(忽略大小写全等)抓游戏帧, 绕开"标题包含"误匹配。

用法: python -B tools/_capture_live.py [输出路径]
找标题 == "starsavior"(忽略大小写)的窗口, PrintWindow 非侵入抓客户区。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starsavior_trainer.capture import (  # noqa: E402
    _capture_client_via_printwindow,
    list_windows,
    save_image,
)

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("screenshots/prejourney_live_001.png")

target = None
for info in list_windows():
    if info.title.strip().lower() == "starsavior":
        target = info
        break
if target is None:
    print("没找到标题精确为 StarSavior 的窗口; 可见窗口:")
    for info in list_windows():
        print(" -", repr(info.title))
    sys.exit(1)

image = _capture_client_via_printwindow(target.hwnd)
if image is None:
    print(f"PrintWindow 抓取失败 hwnd={target.hwnd}")
    sys.exit(2)

path = save_image(image, out)
print(f"captured exact window='{target.title}' hwnd={target.hwnd} size={image.width}x{image.height} -> {path}")
