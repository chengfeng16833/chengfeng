from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from starsavior_trainer.models import Action, Rect


@dataclass(frozen=True)
class ExecutionResult:
    executed: bool
    kind: str
    point: tuple[int, int] | None
    reason: str


class ActionExecutor(Protocol):
    def execute(self, action: Action) -> ExecutionResult:
        raise NotImplementedError


class DryRunExecutor:
    def execute(self, action: Action) -> ExecutionResult:
        point = _click_point(action.target)
        return ExecutionResult(
            executed=False,
            kind=action.kind,
            point=point,
            reason=f"dry run: {action.reason}",
        )


class PyAutoGuiExecutor:
    def __init__(self, move_duration: float = 0.05):
        try:
            import pyautogui
        except ImportError as exc:
            raise RuntimeError("pyautogui is not installed") from exc

        self._pyautogui = pyautogui
        self._move_duration = move_duration

    def execute(self, action: Action) -> ExecutionResult:
        if action.kind not in ("click", "move", "scroll"):
            return ExecutionResult(False, action.kind, None, f"not executable action: {action.reason}")
        point = _click_point(action.target)
        if point is None:
            return ExecutionResult(False, action.kind, None, f"{action.kind} action missing target: {action.reason}")

        self._pyautogui.moveTo(point[0], point[1], duration=self._move_duration)
        if action.kind == "move":
            return ExecutionResult(True, action.kind, point, action.reason)
        if action.kind == "scroll":
            self._drag_scroll(point, action.scroll_clicks)
            return ExecutionResult(True, action.kind, point, action.reason)
        self._pyautogui.click()
        return ExecutionResult(True, action.kind, point, action.reason)

    def _drag_scroll(self, anchor: tuple[int, int], clicks: int, pixels: int = 380, steps: int = 25) -> None:
        """Scroll a list with a real press-hold-drag.

        This game ignores synthetic mouse-wheel events, so we drag instead. We
        use low-level ``mouse_event`` (not pyautogui) because pyautogui moves the
        cursor with SetCursorPos, which produces no real motion trace — the game
        then reads the gesture as a plain click rather than a drag. Sending
        relative MOUSEEVENTF_MOVE deltas while the left button is held gives a
        genuine drag the game accepts.

        ``clicks < 0`` means "scroll down" (look further down the list) → drag the
        content upward; ``clicks > 0`` drags downward.
        """
        import ctypes
        import time

        MOUSEEVENTF_MOVE = 0x0001
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        user32 = ctypes.windll.user32

        dy_total = -pixels if clicks < 0 else pixels
        user32.SetCursorPos(int(anchor[0]), int(anchor[1]))
        time.sleep(0.2)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.3)  # hold before moving so the game registers a press, not a tap
        step_dy = int(dy_total / steps) or (-1 if dy_total < 0 else 1)
        for _ in range(steps):
            user32.mouse_event(MOUSEEVENTF_MOVE, 0, step_dy, 0, 0)
            time.sleep(0.015)
        time.sleep(0.2)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.1)
        # Snap the cursor back to the anchor so repeated drags don't walk it out
        # of the game window (each drag moves relatively from the current point).
        user32.SetCursorPos(int(anchor[0]), int(anchor[1]))


def map_action_to_rect(action: Action, source_resolution: tuple[int, int], dest_rect: Rect) -> Action:
    """Map an action target from screenshot coordinates into a screen rectangle."""
    if action.target is None:
        return action

    source_width, source_height = source_resolution
    scale_x = dest_rect.width / source_width
    scale_y = dest_rect.height / source_height
    target = action.target
    return Action(
        kind=action.kind,
        target=Rect(
            dest_rect.x + round(target.x * scale_x),
            dest_rect.y + round(target.y * scale_y),
            max(round(target.width * scale_x), 1),
            max(round(target.height * scale_y), 1),
        ),
        reason=action.reason,
        confidence=action.confidence,
        scroll_clicks=action.scroll_clicks,
    )


def _click_point(rect: Rect | None) -> tuple[int, int] | None:
    if rect is None:
        return None
    return rect.center
