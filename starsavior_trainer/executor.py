from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Any, Protocol

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

        # Emergency stop: slam the mouse into ANY screen corner to abort the bot.
        # This is the only "reclaim control" path that survives a focused,
        # higher-privilege game window — the F9/F12 keyboard hotkey relies on a
        # global keyboard hook that a low-privilege python can't receive while an
        # admin/Steam window has focus. FAILSAFE is pure cursor-position polling
        # inside our own process, so it fires regardless of focus or privilege.
        pyautogui.FAILSAFE = True
        try:
            width, height = pyautogui.size()
            pyautogui.FAILSAFE_POINTS = [
                (0, 0),
                (width - 1, 0),
                (0, height - 1),
                (width - 1, height - 1),
            ]
        except Exception:
            # size() can fail on a headless host — keep pyautogui's default
            # top-left (0, 0) failsafe point rather than crash.
            pass

    def execute(self, action: Action) -> ExecutionResult:
        if action.kind not in ("click", "move", "scroll"):
            return ExecutionResult(False, action.kind, None, f"not executable action: {action.reason}")
        point = _click_point(action.target)
        if point is None:
            return ExecutionResult(False, action.kind, None, f"{action.kind} action missing target: {action.reason}")

        if action.kind == "move":
            self._hover_move(point)
            return ExecutionResult(True, action.kind, point, action.reason)
        self._pyautogui.moveTo(point[0], point[1], duration=self._move_duration)
        if action.kind == "scroll":
            self._drag_scroll(point, action.scroll_clicks)
            return ExecutionResult(True, action.kind, point, action.reason)
        # repeat > 1 turns the click into a rapid burst for "tap to continue /
        # skip" advance screens (reward popup, dialogue, post-training) so we
        # don't crawl one click per loop iteration.
        repeat = max(1, action.repeat)
        self._pyautogui.click()
        if repeat > 1:
            import time

            for _ in range(repeat - 1):
                time.sleep(0.18)  # ~5 Hz burst — calm enough not to over-click / overshoot
                self._pyautogui.click()
        return ExecutionResult(True, action.kind, point, action.reason)

    def _hover_move(self, point: tuple[int, int]) -> None:
        """Move so the game registers a HOVER (refreshes the right detail panel).

        pyautogui's moveTo uses SetCursorPos (a teleport) which this game doesn't
        treat as motion — so the hovered card's sub-blessings never show. We slide
        in with relative mouse_event moves (real motion), then dwell so the detail
        panel updates before the next capture reads it.
        """
        import ctypes
        import time

        MOUSEEVENTF_MOVE = 0x0001
        user32 = ctypes.windll.user32
        tx, ty = int(point[0]), int(point[1])
        user32.SetCursorPos(tx - 60, ty)  # start left of the target
        time.sleep(0.05)
        for _ in range(12):  # slide right into the target -> real motion events
            user32.mouse_event(MOUSEEVENTF_MOVE, 5, 0, 0, 0)
            time.sleep(0.015)
        user32.SetCursorPos(tx, ty)  # land exactly on the target
        time.sleep(0.4)  # dwell so the hovered card's detail panel refreshes

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
        time.sleep(0.1)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.18)  # hold before moving so the game registers a press, not a tap
        step_dy = int(dy_total / steps) or (-1 if dy_total < 0 else 1)
        for _ in range(steps):
            user32.mouse_event(MOUSEEVENTF_MOVE, 0, step_dy, 0, 0)
            time.sleep(0.008)
        time.sleep(0.12)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.05)
        # Snap the cursor back to the anchor so repeated drags don't walk it out
        # of the game window (each drag moves relatively from the current point).
        user32.SetCursorPos(int(anchor[0]), int(anchor[1]))


# ===================== SendInput (Win32 硬件级输入) =====================
# 常量与结构体定义与源项目 Starsavior-master/src/controller.py 完全一致。
# 这些只是普通的 ctypes 结构体声明, 在任何平台上 import 都不会崩 —— 真正的
# Windows API (ctypes.windll.user32) 直到 SendInputExecutor 构造时才解析。

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
SM_CXSCREEN = 0
SM_CYSCREEN = 1
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
# 数字键 1-4 (事件选项热键), 键码与源项目一致 (VK_1..VK_4 = '1'..'4')
VK_NUMBER_KEYS = {1: 0x31, 2: 0x32, 3: 0x33, 4: 0x34}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("union", INPUT_UNION),
    ]


def _windows_user32() -> Any:
    """Resolve the real Win32 user32 with a clear error on non-Windows hosts.

    Deliberately NOT done at import time so this module keeps importing fine
    everywhere — the DryRun/pyautogui paths must never be affected by this
    Windows-only executor.
    """
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise RuntimeError(
            "SendInputExecutor requires the Win32 user32 API (Windows only); "
            "use DryRunExecutor/PyAutoGuiExecutor on this platform, "
            "or inject a fake user32 in tests."
        )
    try:
        return windll.user32
    except OSError as exc:  # pragma: no cover - 防御性: Windows 上几乎不可能触发
        raise RuntimeError("SendInputExecutor could not load user32.dll") from exc


class SendInputExecutor:
    """Hardware-level click/key executor using Win32 ``SendInput``.

    Ported from the source project's controller.py: Unity/DirectX games that
    swallow pyautogui's SetCursorPos+click still respond to SendInput, because
    the events are injected into the system input queue exactly like real
    hardware. 行为对齐源项目: 点击前保存光标位置、点完还原, 尽量不打扰正在用
    机器的人; 键码 (ESC/空格/数字 1-4) 与源项目一致。

    ``user32`` is injectable: tests pass a fake recorder so nothing real gets
    clicked, and the real ``ctypes.windll.user32`` is only resolved at
    construction time. Screen size is read via ``user32.GetSystemMetrics``,
    so the same fake also controls the pixel→absolute(0-65535) conversion.
    """

    def __init__(
        self,
        user32: Any = None,
        move_settle: float = 0.05,
        down_up_delay: float = 0.06,
        repeat_interval: float = 0.18,
        key_hold: float = 0.05,
        key_settle: float = 0.1,
    ):
        self._user32 = user32 if user32 is not None else _windows_user32()
        # 时序参数(秒): 取源项目随机区间的中值附近, 改成确定值方便测试与复现;
        # repeat_interval 对齐 PyAutoGuiExecutor 的 ~5Hz burst。测试全传 0 即瞬时跑完。
        self._move_settle = move_settle
        self._down_up_delay = down_up_delay
        self._repeat_interval = repeat_interval
        self._key_hold = key_hold
        self._key_settle = key_settle

    def execute(self, action: Action) -> ExecutionResult:
        if action.kind != "click":
            # move(悬停)/scroll(拖拽) 依赖真实的相对位移轨迹 (见 PyAutoGuiExecutor
            # 的 _hover_move/_drag_scroll), 源项目没有对应的 SendInput 实现 ——
            # 不在这里硬造, 交还调用方决定 (可与 PyAutoGuiExecutor 混用)。
            return ExecutionResult(
                False,
                action.kind,
                None,
                f"sendinput executor does not implement {action.kind}: {action.reason}",
            )
        point = _click_point(action.target)
        if point is None:
            return ExecutionResult(False, action.kind, None, f"click action missing target: {action.reason}")

        import time

        # 1. 保存当前光标位置 (点完还原 —— 源项目行为)。
        saved = POINT()
        self._user32.GetCursorPos(ctypes.byref(saved))

        # 2. 点击; 多连点次数由 action.repeat 控制 (与 PyAutoGuiExecutor 的 burst
        #    语义一致)。每次按下前都重发绝对移动, 物理鼠标中途被碰一下也不会点偏
        #    (源项目的 click_center_multi 每次点击也会先 move)。
        repeat = max(1, action.repeat)
        for i in range(repeat):
            self._send_move(point[0], point[1])
            time.sleep(self._move_settle)
            self._send_mouse_event(MOUSEEVENTF_LEFTDOWN)
            time.sleep(self._down_up_delay)
            self._send_mouse_event(MOUSEEVENTF_LEFTUP)
            if i < repeat - 1:
                time.sleep(self._repeat_interval)

        # 3. 还原光标到点击前位置。
        self._send_move(saved.x, saved.y)
        return ExecutionResult(True, action.kind, point, action.reason)

    # ===================== 键盘 (键码与源项目一致) =====================

    def send_escape(self) -> None:
        """发送 ESC 键 (关菜单/取消)。"""
        self._press_key(VK_ESCAPE)

    def send_space(self) -> None:
        """发送空格键 (跳过战斗兜底)。"""
        self._press_key(VK_SPACE)

    def send_number_key(self, n: int) -> None:
        """发送数字键 1-4 (事件选项热键); 范围外静默忽略 (源项目行为)。"""
        vk = VK_NUMBER_KEYS.get(n)
        if vk is None:
            return
        self._press_key(vk)

    # ===================== 内部实现 =====================

    def _press_key(self, vk_code: int) -> None:
        """按下→保持→释放→停顿, 序列与源项目一致 (0.05s hold / 0.1s settle)。"""
        import time

        self._send_key(vk_code, key_up=False)
        time.sleep(self._key_hold)
        self._send_key(vk_code, key_up=True)
        time.sleep(self._key_settle)

    def _send_move(self, screen_x: int, screen_y: int) -> None:
        """移动光标到屏幕绝对坐标 (SendInput MOVE|ABSOLUTE)。"""
        self._send_mouse_input(screen_x, screen_y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)

    def _send_mouse_event(self, flags: int) -> None:
        """在当前光标位置发送鼠标事件 (LEFTDOWN/LEFTUP, 不带 ABSOLUTE)。"""
        self._send_mouse_input(0, 0, flags)

    def _send_mouse_input(self, dx: int, dy: int, flags: int) -> None:
        """SendInput 底层调用 (鼠标)。

        像素 → 绝对坐标公式与源项目一致: int(pixel * 65535 / 屏幕宽或高),
        屏幕尺寸通过注入的 user32.GetSystemMetrics 读取。
        """
        screen_w = self._user32.GetSystemMetrics(SM_CXSCREEN)
        screen_h = self._user32.GetSystemMetrics(SM_CYSCREEN)
        normalized_x = int((dx * 65535) / screen_w) if screen_w > 0 else 0
        normalized_y = int((dy * 65535) / screen_h) if screen_h > 0 else 0

        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi = MOUSEINPUT()
        inp.union.mi.dx = normalized_x
        inp.union.mi.dy = normalized_y
        inp.union.mi.mouseData = 0
        inp.union.mi.dwFlags = flags
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _send_key(self, vk_code: int, key_up: bool = False) -> None:
        """SendInput 键盘事件。"""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki = KEYBDINPUT()
        inp.union.ki.wVk = vk_code
        inp.union.ki.wScan = 0
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


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
        repeat=action.repeat,
    )


def _click_point(rect: Rect | None) -> tuple[int, int] | None:
    if rect is None:
        return None
    return rect.center
