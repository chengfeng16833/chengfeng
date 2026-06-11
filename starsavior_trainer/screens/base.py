"""Screen handler protocol — the contract every screen registers against.

Goal (audit dimension 5): adding a new screen should mean writing ONE handler
file + one registry line + region JSON, instead of editing models / classifier /
screen_reader / policy / live_loop separately.

A handler bundles the three per-screen concerns:
- ``has_anchor``  — is the current screen this one? (used by the classifier)
- ``parse``       — turn OCR'd region texts into a structured payload
- ``decide``      — choose an Action for an Observation of this screen

To keep behaviour 1:1 with the pre-refactor code during the migration, handlers
DELEGATE to the existing, already-tested functions (``parse_X`` in
screen_reader, ``_has_X_signature`` in classifier, ``decide_X`` in policy).
``decide`` receives the ``TrainerPolicy`` instance because the existing decision
logic depends on its config (button coords, thresholds) and instance state
(e.g. the commission two-step). This is intentional and documented, not a leak.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional, Protocol, runtime_checkable

from PIL import Image

from starsavior_trainer.models import Action, GameState, Observation, Screen
from starsavior_trainer.regions import RegionProfile

if TYPE_CHECKING:  # avoid a runtime import cycle with policy
    from starsavior_trainer.policy import TrainerPolicy


@runtime_checkable
class ScreenHandler(Protocol):
    """The contract a screen handler must satisfy."""

    screen: Screen
    # Lower priority is checked first during classification. Mirrors the original
    # ordered _match_screen signature checks so behaviour stays identical.
    priority: int

    def has_anchor(self, anchors: dict[str, str]) -> tuple[bool, float]:
        """Return (is_this_screen, confidence) from the OCR'd anchor texts."""
        ...

    def parse(
        self,
        region_texts: object,
        profile: RegionProfile,
        image: Optional[Image.Image] = None,
    ) -> object | None:
        """Build this screen's structured payload, or None if not parseable."""
        ...

    def decide(self, observation: Observation, state: GameState, policy: "TrainerPolicy") -> Action:
        """Choose an Action for an Observation of this screen."""
        ...


class DelegatingScreenHandler:
    """Concrete handler that forwards to existing functions (1:1 behaviour).

    Each screen wires the already-tested ``_has_X_signature`` / ``parse_X`` /
    ``decide_X`` callables here, so the registry changes the *dispatch* without
    changing any decision or parsing logic.
    """

    def __init__(
        self,
        screen: Screen,
        decide_fn: Callable[[Observation, GameState, "TrainerPolicy"], Action],
        *,
        priority: int = 1000,
        anchor_fn: Optional[Callable[[dict[str, str]], bool]] = None,
        anchor_confidence: float = 1.0,
        parse_fn: Optional[Callable[..., object | None]] = None,
        parse_needs_image: bool = False,
        parse_needs_ocr: bool = False,
        ocr_prefixes: Optional[list[str]] = None,
    ) -> None:
        self.screen = screen
        self.priority = priority
        self._decide_fn = decide_fn
        self._anchor_fn = anchor_fn
        self._anchor_confidence = anchor_confidence
        self._parse_fn = parse_fn
        self._parse_needs_image = parse_needs_image
        # parse 需要 OCR 引擎做 bbox 级文字定位(read_lines)时置 True ——
        # 滚动弹窗里按钮位置不固定, 用「找到目标词→点词中心」代替固定坐标。
        self._parse_needs_ocr = parse_needs_ocr
        # Region-name prefixes to OCR before parsing (used by the live loop).
        # None means this screen needs no OCR payload (policy clicks a fixed button).
        self.ocr_prefixes = ocr_prefixes

    def has_anchor(self, anchors: dict[str, str]) -> tuple[bool, float]:
        if self._anchor_fn is None:
            return (False, 0.0)
        return (True, self._anchor_confidence) if self._anchor_fn(anchors) else (False, 0.0)

    def parse(
        self,
        region_texts: object,
        profile: RegionProfile,
        image: Optional[Image.Image] = None,
        ocr: object | None = None,
    ) -> object | None:
        if self._parse_fn is None:
            return None
        if self._parse_needs_ocr:
            return self._parse_fn(region_texts, profile, image, ocr)
        if self._parse_needs_image:
            return self._parse_fn(region_texts, profile, image)
        return self._parse_fn(region_texts, profile)

    def decide(self, observation: Observation, state: GameState, policy: "TrainerPolicy") -> Action:
        return self._decide_fn(observation, state, policy)
