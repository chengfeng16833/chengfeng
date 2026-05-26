from __future__ import annotations

import argparse

from PIL import Image

from starsavior_trainer.ocr import NoopOcrEngine, PaddleOcrEngine
from starsavior_trainer.regions import load_region_profile, scale_region_profile
from starsavior_trainer.screen_reader import RegionOcrReader


def main() -> None:
    parser = argparse.ArgumentParser(description="Read OCR text from configured screenshot regions.")
    parser.add_argument("--image", required=True, help="Input screenshot.")
    parser.add_argument("--profile", default="config/regions/1920x1080.json", help="Region profile JSON.")
    parser.add_argument("--engine", choices=["noop", "paddle"], default="noop")
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Only OCR regions with this prefix. Repeat for multiple prefixes.",
    )
    parser.add_argument(
        "--max-area",
        type=int,
        default=120000,
        help="Skip larger regions by default to avoid slow whole-panel OCR. Use 0 to disable.",
    )
    parser.add_argument(
        "--all-regions",
        action="store_true",
        help="OCR every configured region. Slow with PaddleOCR; prefer --prefix for normal use.",
    )
    args = parser.parse_args()

    image = Image.open(args.image)
    profile = scale_region_profile(load_region_profile(args.profile), image.size)
    ocr = PaddleOcrEngine() if args.engine == "paddle" else NoopOcrEngine()
    reader = RegionOcrReader(profile, ocr)
    max_area = None if args.max_area == 0 else args.max_area

    if args.prefix:
        results = reader.read_prefixes(image, args.prefix, max_area=max_area)
    elif args.all_regions:
        results = reader.read_all(image, max_area=max_area)
    else:
        results = reader.read_ocr_regions(image, max_area=max_area)

    for result in results:
        print(f"{result.name}\t{result.confidence:.2f}\t{result.text}")


if __name__ == "__main__":
    main()
