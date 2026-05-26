from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starsavior_trainer.models import Rect


@dataclass(frozen=True)
class RegionProfile:
    name: str
    resolution: tuple[int, int]
    regions: dict[str, Rect]


def load_region_profile(path: str | Path) -> RegionProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    resolution = data.get("resolution")
    if not isinstance(resolution, list) or len(resolution) != 2:
        raise ValueError("profile resolution must be [width, height]")

    regions: dict[str, Rect] = {}
    raw_regions = data.get("regions", {})
    if not isinstance(raw_regions, dict):
        raise ValueError("profile regions must be an object")

    for name, raw_rect in raw_regions.items():
        regions[name] = _parse_rect(raw_rect, f"regions.{name}")

    return RegionProfile(
        name=str(data.get("name", Path(path).stem)),
        resolution=(int(resolution[0]), int(resolution[1])),
        regions=regions,
    )


def scale_region_profile(profile: RegionProfile, resolution: tuple[int, int]) -> RegionProfile:
    """Scale a region profile to match an image with the same UI layout."""
    if profile.resolution == resolution:
        return profile

    base_width, base_height = profile.resolution
    target_width, target_height = resolution
    scale_x = target_width / base_width
    scale_y = target_height / base_height
    return RegionProfile(
        name=f"{profile.name}@{target_width}x{target_height}",
        resolution=resolution,
        regions={
            name: Rect(
                round(rect.x * scale_x),
                round(rect.y * scale_y),
                max(round(rect.width * scale_x), 1),
                max(round(rect.height * scale_y), 1),
            )
            for name, rect in profile.regions.items()
        },
    )


def _parse_rect(value: Any, label: str) -> Rect:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{label} must be [x, y, width, height]")
    x, y, width, height = (int(part) for part in value)
    if width <= 0 or height <= 0:
        raise ValueError(f"{label} width and height must be positive")
    return Rect(x, y, width, height)
