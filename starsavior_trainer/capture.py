from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageGrab

from starsavior_trainer.models import Rect


def _set_dpi_awareness() -> None:
    """Make the process DPI-aware so window/screen coords use physical pixels.

    Without this, GetClientRect/ClientToScreen return virtualized logical
    coordinates while ImageGrab returns physical pixels, so the client-area
    crop lands on the wrong region under display scaling (e.g. 150% on 4K).
    Must run before any window or grab call.
    """
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_set_dpi_awareness()


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    rect: Rect


def capture_screen() -> Image.Image:
    return ImageGrab.grab()


def capture_window(title_contains: str, target_width: int = 2560, target_height: int = 1440) -> tuple[Image.Image, WindowInfo]:
    """Capture the game window client area and scale to target resolution.

    Uses GetClientRect for accurate client-area dimensions, crops out
    borders/titlebar, and scales to `target_width x target_height` so
    region profiles at the target resolution work directly.
    """
    window = find_window(title_contains)
    if window is None:
        raise RuntimeError(f"window not found: {title_contains}")

    client_rect = wintypes.RECT()
    ctypes.windll.user32.GetClientRect(window.hwnd, ctypes.byref(client_rect))
    client_w = client_rect.right
    client_h = client_rect.bottom

    if client_w <= 0 or client_h <= 0:
        raise RuntimeError(f"invalid client rect: {client_w}x{client_h}")

    pt = wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(window.hwnd, ctypes.byref(pt))

    _bring_to_front(window.hwnd)
    full = ImageGrab.grab()
    client_img = full.crop((pt.x, pt.y, pt.x + client_w, pt.y + client_h))

    if (client_w, client_h) != (target_width, target_height):
        client_img = client_img.resize((target_width, target_height), Image.LANCZOS)

    client_window = WindowInfo(window.hwnd, window.title, Rect(pt.x, pt.y, client_w, client_h))
    return client_img, client_window


def save_image(image: Image.Image, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output


def find_window(title_contains: str) -> WindowInfo | None:
    needle = title_contains.casefold()
    matches: list[WindowInfo] = []

    def visit(hwnd: int) -> bool:
        if not _is_window_visible(hwnd):
            return True
        title = _get_window_text(hwnd)
        if title and needle in title.casefold():
            rect = _get_window_rect(hwnd)
            if rect.width > 0 and rect.height > 0:
                matches.append(WindowInfo(hwnd=hwnd, title=title, rect=rect))
        return True

    _enum_windows(visit)
    return matches[0] if matches else None


def list_windows() -> list[WindowInfo]:
    windows: list[WindowInfo] = []

    def visit(hwnd: int) -> bool:
        if not _is_window_visible(hwnd):
            return True
        title = _get_window_text(hwnd)
        if title:
            rect = _get_window_rect(hwnd)
            if rect.width > 0 and rect.height > 0:
                windows.append(WindowInfo(hwnd=hwnd, title=title, rect=rect))
        return True

    _enum_windows(visit)
    return windows


def _bring_to_front(hwnd: int) -> None:
    import time
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def _enum_windows(callback: Callable[[int], bool]) -> None:
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def wrapped(hwnd: int, _lparam: int) -> bool:
        return callback(hwnd)

    ctypes.windll.user32.EnumWindows(enum_proc(wrapped), 0)


def _is_window_visible(hwnd: int) -> bool:
    return bool(ctypes.windll.user32.IsWindowVisible(hwnd))


def _get_window_text(hwnd: int) -> str:
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _get_window_rect(hwnd: int) -> Rect:
    raw = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(raw)):
        raise ctypes.WinError()
    return Rect(raw.left, raw.top, raw.right - raw.left, raw.bottom - raw.top)
