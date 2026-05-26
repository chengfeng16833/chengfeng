"""Test blue button classifier on scaled screenshot."""
from pathlib import Path
from PIL import Image
from starsavior_trainer.classifier import classify_by_blue_button, UNIQUE_BLUE_BUTTONS
from starsavior_trainer.classifier import _BOTTOM_RIGHT_BUTTONS
from starsavior_trainer.regions import load_region_profile
from starsavior_trainer.vision import BlueButtonDetector
from starsavior_trainer.image_regions import crop_region

profile = load_region_profile("config/regions/2560x1440.json")
detector = BlueButtonDetector()

# Test with scaled image
scaled_path = Path("screenshots/scaled_2560.png")
if not scaled_path.exists():
    print("No scaled_2560.png found, testing with other screenshots scaled manually...")
    # Try real_001.png
    real_path = Path("screenshots/real_001.png")
    fullscreen_path = Path("screenshots/fullscreen.png")
    if real_path.exists():
        img = Image.open(real_path)
        img = img.resize((2560, 1440), Image.LANCZOS)
        print(f"Scaled {real_path.name} from {Image.open(real_path).size} to 2560x1440")
    elif fullscreen_path.exists():
        img = Image.open(fullscreen_path)
        img = img.resize((2560, 1440), Image.LANCZOS)
        print(f"Scaled {fullscreen_path.name} from {Image.open(fullscreen_path).size} to 2560x1440")
    else:
        print("No test images available")
        exit(1)
else:
    img = Image.open(scaled_path)
    print(f"Using {scaled_path.name}: {img.size[0]}x{img.size[1]}")

print()

# Test all blue button regions
for region_name, screen in UNIQUE_BLUE_BUTTONS.items():
    rect = profile.regions.get(region_name)
    if rect is None:
        print(f"  {region_name}: NOT IN PROFILE")
        continue
    try:
        crop = crop_region(img, rect)
        signal = detector.detect(crop)
        marker = " *** BLUE ***" if signal.name == "active_blue" else ""
        print(f"  {region_name}: {signal.name} c={signal.confidence:.2f} cov={signal.coverage:.3f} -> {screen.value}{marker}")
    except Exception as e:
        print(f"  {region_name}: ERROR {e}")

print()
for region_name, screen in _BOTTOM_RIGHT_BUTTONS:
    rect = profile.regions.get(region_name)
    if rect is None:
        print(f"  {region_name}: NOT IN PROFILE")
        continue
    try:
        crop = crop_region(img, rect)
        signal = detector.detect(crop)
        marker = " *** BLUE ***" if signal.name == "active_blue" else ""
        print(f"  {region_name}: {signal.name} c={signal.confidence:.2f} cov={signal.coverage:.3f} -> {screen.value}{marker}")
    except Exception as e:
        print(f"  {region_name}: ERROR {e}")

print()
obs = classify_by_blue_button(img, profile)
print(f"Classification: {obs.screen.value} (confidence={obs.confidence:.2f})")
