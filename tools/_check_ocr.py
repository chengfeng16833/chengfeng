import os, logging
os.environ["FLAGS_use_mkldnn"] = "0"
logging.disable(logging.CRITICAL)

from PIL import Image
from starsavior_trainer.ocr import PaddleOcrEngine
from starsavior_trainer.image_regions import crop_region
from starsavior_trainer.models import Rect

img = Image.open(r"screenshots\real_001.png")
print(f"Image: {img.width}x{img.height}")

engine = PaddleOcrEngine()
w, h = img.width, img.height

regions = {
    "L1_top":        Rect(30,       30,  450, 80),
    "L2_mid":        Rect(30,       h//3, 450, 120),
    "R1_top":        Rect(w - 650,  30,  630, 80),
    "R2_mid":        Rect(w - 700,  h//3, 680, 200),
    "R3_bot":        Rect(w - 550,  h - 130, 530, 80),
}

for name, rect in regions.items():
    try:
        crop = crop_region(img, rect)
        result = engine.read_text(crop)
        txt = result.text.strip()[:150] if result.text.strip() else "(empty)"
        print(f"  {name}: '{txt}' (conf={result.confidence:.2f})")
    except Exception as e:
        print(f"  {name}: error={type(e).__name__}")
