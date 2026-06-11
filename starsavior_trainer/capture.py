from __future__ import annotations

import ctypes
import threading
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


_PW_RENDERFULLCONTENT = 2  # PrintWindow flag for DWM/hardware-accelerated content
_PRINTWINDOW_TIMEOUT_SECONDS = 5.0


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def _capture_client_via_printwindow(hwnd: int) -> Image.Image | None:
    """Capture a window's client area via PrintWindow — robust to occlusion.

    PrintWindow copies the window's *own* pixels into a bitmap regardless of
    z-order, so it works even when the game is behind another window or not in
    the foreground — unlike ImageGrab, which only sees whatever is physically on
    screen at those coordinates (and so silently captures the wrong window when
    SetForegroundWindow is blocked). PW_RENDERFULLCONTENT (flag 2) is required
    for DWM/hardware-accelerated windows like Unity games.

    Renders the whole window (incl. title bar / borders) then crops out the
    client area, so it is correct for both borderless and windowed modes.
    Returns None if PrintWindow fails or yields an all-black frame, so the
    caller can fall back to a screen grab.
    """
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    win_rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(win_rect)):
        return None
    win_w = win_rect.right - win_rect.left
    win_h = win_rect.bottom - win_rect.top

    client_rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))
    client_w = client_rect.right
    client_h = client_rect.bottom
    if win_w <= 0 or win_h <= 0 or client_w <= 0 or client_h <= 0:
        return None

    # Client top-left offset within the full window (title bar + border width).
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    off_x = origin.x - win_rect.left
    off_y = origin.y - win_rect.top

    window_dc = user32.GetWindowDC(hwnd)
    if not window_dc:
        return None
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, win_w, win_h)
    try:
        gdi32.SelectObject(mem_dc, bitmap)
        if not user32.PrintWindow(hwnd, mem_dc, _PW_RENDERFULLCONTENT):
            return None

        header = _BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        header.biWidth = win_w
        header.biHeight = -win_h  # negative => top-down rows
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0  # BI_RGB

        buffer = (ctypes.c_char * (win_w * win_h * 4))()
        if not gdi32.GetDIBits(mem_dc, bitmap, 0, win_h, buffer, ctypes.byref(header), 0):
            return None
        full = Image.frombuffer("RGB", (win_w, win_h), buffer, "raw", "BGRX", 0, 1)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, window_dc)

    client = full.crop((off_x, off_y, off_x + client_w, off_y + client_h))
    if client.convert("L").getextrema() == (0, 0):
        return None  # all-black capture -> signal caller to fall back
    return client


def _run_capture_with_timeout(capture: Callable[[], Image.Image | None], timeout_seconds: float) -> Image.Image | None:
    result: list[Image.Image | None] = [None]
    error: list[BaseException | None] = [None]

    def worker() -> None:
        try:
            result[0] = capture()
        except BaseException as exc:
            error[0] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    if thread.is_alive() or error[0] is not None:
        return None
    return result[0]


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

    # Capture via PrintWindow: grabs the game's own pixels even when the window
    # is covered or unfocused, so capture itself no longer needs to steal focus.
    # Fall back to a screen grab + crop only if PrintWindow fails (that path does
    # need the window visible, so activate it first).
    client_img = _run_capture_with_timeout(
        lambda: _capture_client_via_printwindow(window.hwnd),
        _PRINTWINDOW_TIMEOUT_SECONDS,
    )
    if client_img is None:
        activate_window(window.hwnd)
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
    """按标题找窗口: 精确相等(忽略大小写)优先, 其次才是包含匹配。

    没有精确优先时, 桌面上开着 "starsavior-trainer - 文件资源管理器" 这类
    标题包含游戏名的窗口会按 Z 序截胡真正的 "StarSavior" 游戏窗口(实测踩过)。
    """
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
    for info in matches:
        if info.title.strip().casefold() == needle:
            return info
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


def activate_window(hwnd: int) -> None:
    """Force a window to the foreground so it receives synthetic mouse input.

    A plain SetForegroundWindow is refused by Windows when the caller isn't the
    current foreground process (anti focus-stealing). We use the standard
    AttachThreadInput trick: temporarily attach our input queue to the current
    foreground thread (and the target's) to lift that restriction.

    This is required for clicks/scrolls to actually reach the game: Unity titles
    only process mouse input while they are the *active* window, and Windows
    routes the mouse-wheel message to the focused window — so the game must be
    foreground at the instant pyautogui sends the event.
    """
    import time

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.c_void_p)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    SW_RESTORE = 9

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    fg_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0

    attached_fg = attached_target = False
    try:
        if fg_thread and fg_thread != current_thread:
            attached_fg = bool(user32.AttachThreadInput(current_thread, fg_thread, True))
        if target_thread and target_thread != current_thread:
            attached_target = bool(user32.AttachThreadInput(current_thread, target_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached_target:
            user32.AttachThreadInput(current_thread, target_thread, False)
        if attached_fg:
            user32.AttachThreadInput(current_thread, fg_thread, False)
    time.sleep(0.12)


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
