import os, logging, ctypes, time
os.environ["FLAGS_use_mkldnn"] = "0"
logging.disable(logging.CRITICAL)

hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
ctypes.windll.user32.ShowWindow(hwnd_console, 6)
time.sleep(0.5)

from starsavior_trainer.capture import capture_window
from starsavior_trainer.ocr import PaddleOcrEngine
from starsavior_trainer.image_regions import crop_region
from starsavior_trainer.models import Rect

img, win = capture_window("StarSavior")
ctypes.windll.user32.ShowWindow(hwnd_console, 9)

engine = PaddleOcrEngine()
W, H = img.width, img.height

# Read the entire image at once
result = engine.read_text(img)
print(f"Full image OCR ({W}x{H}):")
print(f"  '{result.text[:400]}'")

# Grep for specific keywords
keywords = ["选择", "旅程", "起点", "力量", "体力", "开始", "确认", "SKIP", "RANK", "训练"]
for kw in keywords:
    if kw in result.text:
        print(f"  FOUND: '{kw}'")
