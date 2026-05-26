"""Quick smoke test for blue-button classifier and live_loop blue mode."""
from starsavior_trainer.classifier import (
    classify_by_blue_button,
    UNIQUE_BLUE_BUTTONS,
    _region_content_density,
    _classify_bottom_right_group,
)
from PIL import Image

# Test 1: Basic imports and data structures
print(f"Unique blue buttons: {len(UNIQUE_BLUE_BUTTONS)} screens")
for region, screen in UNIQUE_BLUE_BUTTONS.items():
    print(f"  {region} -> {screen.value}")

# Test 2: Content density
solid = Image.new("RGB", (100, 50), color=(128, 128, 128))
density = _region_content_density(solid)
print(f"Solid gray density: {density:.3f}")

# Test 3: live_loop blue mode functions
from starsavior_trainer.cli.live_loop import _training_select_blue, _rest_submenu_blue
print("live_loop blue functions imported OK")

print("\nAll smoke tests passed!")
