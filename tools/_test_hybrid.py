"""Smoke test for classify_hybrid and hybrid mode in live_loop."""
from pathlib import Path
from PIL import Image

from starsavior_trainer.classifier import classify_hybrid, UNIQUE_BLUE_BUTTONS, _region_content_density
from starsavior_trainer.cli.live_loop import _read_screen_payload_ocr, _read_screen_payload_blue, _training_select_blue, _rest_submenu_blue
from starsavior_trainer.regions import load_region_profile
from starsavior_trainer.ocr import NoopOcrEngine

print(f"classify_hybrid: {classify_hybrid}")
print(f"unique blue buttons: {len(UNIQUE_BLUE_BUTTONS)}")
print("live_loop hybrid functions imported OK")

solid = Image.new("RGB", (100, 50), color=(128, 128, 128))
density = _region_content_density(solid)
print(f"solid density: {density:.3f}")

scaled_path = Path("screenshots/scaled_2560.png")
if scaled_path.exists():
    profile = load_region_profile("config/regions/2560x1440.json")
    img = Image.open(scaled_path)
    ocr = NoopOcrEngine()
    obs = classify_hybrid(img, profile, ocr)
    print(f"hybrid on scaled_2560: {obs.screen.value} (conf={obs.confidence:.2f})")

print("\nAll hybrid smoke tests passed!")
