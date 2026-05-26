# -*- coding: utf-8 -*-
"""分析星脚本目录中的截图"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image

d = r"C:\Users\ChengFeng\Desktop\星脚本"
for f in sorted(os.listdir(d)):
    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
        path = os.path.join(d, f)
        try:
            w, h = Image.open(path).size
            print(f"  [{w}x{h}] {f}")
        except Exception as e:
            print(f"  [ERROR] {f}: {e}")
