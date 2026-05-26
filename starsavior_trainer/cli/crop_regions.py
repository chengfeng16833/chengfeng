from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from starsavior_trainer.image_regions import draw_region_overlay, export_region_crops
from starsavior_trainer.regions import load_region_profile, scale_region_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop configured Starsavior regions from a screenshot.")
    parser.add_argument("--image", required=True, help="Input screenshot.")
    parser.add_argument("--profile", default="config/regions/1920x1080.json", help="Region profile JSON.")
    parser.add_argument("--out-dir", default="debug/regions", help="Directory for cropped regions.")
    parser.add_argument("--overlay", default="debug/regions-overlay.png", help="Output overlay image path.")
    args = parser.parse_args()

    image = Image.open(args.image)
    profile = scale_region_profile(load_region_profile(args.profile), image.size)
    outputs = export_region_crops(image, profile, args.out_dir)

    overlay = draw_region_overlay(image, profile)
    overlay_path = Path(args.overlay)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(overlay_path)

    print(f"cropped={len(outputs)} out_dir={args.out_dir}")
    print(f"overlay={overlay_path}")


if __name__ == "__main__":
    main()
