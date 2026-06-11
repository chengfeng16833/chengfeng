"""Safe shop profile helpers migrated from Starsavior-master data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starsavior_trainer.profile_loader import ProfileLoadError, load_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_ROOT = PROJECT_ROOT / "config" / "profiles"

SAFE_AUTO_BUY_TYPES = frozenset({"potential_points"})
EFFECT_CONTEXT_KEYWORDS = ("效果", "增加", "退还", "潜质点数")


@dataclass(frozen=True)
class ShopProfileItem:
    id: str
    name: str
    kind: str
    keywords: tuple[str, ...]
    effect_keys: tuple[str, ...]


@dataclass(frozen=True)
class ShopProfile:
    name: str
    items: tuple[ShopProfileItem, ...]

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ShopProfile":
        items: list[ShopProfileItem] = []
        for raw in data.get("items", []):
            if not isinstance(raw, dict):
                continue
            keywords = tuple(str(value).strip() for value in raw.get("keywords", []) if str(value).strip())
            effect_keys = tuple(str(value).strip() for value in raw.get("effect_keys", []) if str(value).strip())
            items.append(
                ShopProfileItem(
                    id=str(raw.get("id", "")).strip(),
                    name=str(raw.get("name", "")).strip(),
                    kind=str(raw.get("type", "")).strip(),
                    keywords=keywords,
                    effect_keys=effect_keys,
                )
            )
        return cls(name=name, items=tuple(items))


def load_shop_profile(root: Path | str = DEFAULT_PROFILE_ROOT, profile_name: str = "speed") -> ShopProfile:
    try:
        record = load_profile(root, "shop", profile_name)
    except ProfileLoadError:
        if profile_name == "default":
            raise
        record = load_profile(root, "shop", "default")
        profile_name = "default"
    return ShopProfile.from_dict(profile_name, record.data)


def shop_effect_worth_buying(effect_text: str, profile: ShopProfile) -> bool:
    text = effect_text.strip()
    if not text or not _looks_like_effect_text(text):
        return False
    for item in profile.items:
        if item.kind not in SAFE_AUTO_BUY_TYPES:
            continue
        if item.kind == "potential_points" and "潜质" in text and ("增加" in text or "退还" in text):
            return True
        if any(key and key in text for key in item.effect_keys):
            return True
        if any(key and key in text and "潜质" in key for key in item.keywords):
            return True
    return False


def _looks_like_effect_text(text: str) -> bool:
    return any(keyword in text for keyword in EFFECT_CONTEXT_KEYWORDS)
