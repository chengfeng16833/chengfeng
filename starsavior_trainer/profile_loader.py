"""Load normalized strategy profiles from JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_PROFILE_KINDS = frozenset({"training", "events", "shop", "skills"})


class ProfileLoadError(ValueError):
    """Raised when a strategy profile cannot be loaded safely."""


@dataclass(frozen=True)
class ProfileRecord:
    kind: str
    name: str
    path: Path
    data: dict[str, Any]


def load_profile(root: Path | str, kind: str, name: str) -> ProfileRecord:
    """Load one named profile from ``root / kind / f\"{name}.json\"``."""
    root_path = Path(root)
    _validate_kind(kind)
    path = root_path / kind / f"{name}.json"
    if not path.exists():
        raise ProfileLoadError(f"Profile file not found: {path}")
    return _read_profile(path, kind, name)


def load_profiles(root: Path | str, kind: str) -> list[ProfileRecord]:
    """Load all profiles for a kind, sorted by filename stem."""
    root_path = Path(root)
    _validate_kind(kind)
    profile_dir = root_path / kind
    if not profile_dir.exists():
        return []
    if not profile_dir.is_dir():
        raise ProfileLoadError(f"Profile path is not a directory: {profile_dir}")
    return [_read_profile(path, kind, path.stem) for path in sorted(profile_dir.glob("*.json"))]


def _validate_kind(kind: str) -> None:
    if kind not in SUPPORTED_PROFILE_KINDS:
        supported = ", ".join(sorted(SUPPORTED_PROFILE_KINDS))
        raise ProfileLoadError(f"Unsupported profile kind: {kind!r}. Supported kinds: {supported}")


def _read_profile(path: Path, kind: str, name: str) -> ProfileRecord:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ProfileLoadError(f"Invalid JSON in profile {path}: {exc}") from exc
    except OSError as exc:
        raise ProfileLoadError(f"Unable to read profile {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileLoadError(f"Profile {path} must contain a JSON object")
    return ProfileRecord(kind=kind, name=name, path=path, data=data)
