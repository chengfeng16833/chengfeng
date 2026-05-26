from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from starsavior_trainer.models import Rect
from starsavior_trainer.regions import RegionProfile


def crop_region(image: Image.Image, rect: Rect) -> Image.Image:
    return image.crop((rect.x, rect.y, rect.x + rect.width, rect.y + rect.height))


def export_region_crops(image: Image.Image, profile: RegionProfile, output_dir: str | Path) -> list[Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for name, rect in profile.regions.items():
        output = root / f"{name}.png"
        crop_region(image, rect).save(output)
        outputs.append(output)
    return outputs


def draw_region_overlay(image: Image.Image, profile: RegionProfile) -> Image.Image:
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    for name, rect in profile.regions.items():
        x1, y1 = rect.x, rect.y
        x2, y2 = rect.x + rect.width, rect.y + rect.height
        draw.rectangle((x1, y1, x2, y2), outline="red", width=3)
        draw.text((x1 + 4, y1 + 4), name, fill="red")
    return overlay
