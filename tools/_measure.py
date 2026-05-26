"""Crop specific regions from screenshots to verify/calibrate coordinates."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw

def show_crop(img, x, y, w, h, label=""):
    crop = img.crop((x, y, x+w, y+h))
    print(f"  [{label}] ({x},{y}) {w}x{h}")
    crop.save(f"debug/_crop_{label.replace(' ','_')}.png")

def annotate(img, regions, out_path):
    copy = img.copy().convert("RGB")
    draw = ImageDraw.Draw(copy)
    for name, (x, y, w, h) in regions.items():
        draw.rectangle([x, y, x+w, y+h], outline=(255, 0, 0), width=2)
        draw.text((x+2, y+2), name[:18], fill=(255, 255, 0))
    copy.save(out_path)
    print(f"Saved: {out_path}")

# Commission select - proposed new regions
commission_img = Image.open("screenshots/commission_select_002.png")
print(f"Commission: {commission_img.size}")
commission_regions = {
    "opt1":     (1690, 330, 810, 120),
    "opt2":     (1690, 455, 810, 120),
    "opt3":     (1690, 580, 810, 120),
    "opt1_name": (1820, 340, 530, 55),
    "opt2_name": (1820, 465, 530, 55),
    "opt3_name": (1820, 590, 530, 55),
    "accept_btn":(1740, 1280, 755, 90),
    "anchor":    (330, 62, 400, 62),
}
annotate(commission_img, commission_regions, "debug/commission_calibrate.png")

# Shop - proposed new regions
shop_img = Image.open("screenshots/shop_002.png")
print(f"Shop: {shop_img.size}")
shop_regions = {
    "item1":    (1640, 310, 840, 110),
    "item2":    (1640, 425, 840, 110),
    "item3":    (1640, 540, 840, 110),
    "item1_nm": (1730, 318, 580, 50),
    "item2_nm": (1730, 433, 580, 50),
    "item3_nm": (1730, 548, 580, 50),
    "item1_pr": (2300, 318, 175, 50),
    "item2_pr": (2300, 433, 175, 50),
    "item3_pr": (2300, 548, 175, 50),
    "buy_btn":  (1650, 1285, 820, 85),
    "anchor":   (330, 62, 400, 62),
}
annotate(shop_img, shop_regions, "debug/shop_calibrate.png")
