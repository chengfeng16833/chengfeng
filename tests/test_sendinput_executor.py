import unittest
from unittest import mock

from starsavior_trainer import executor as executor_module
from starsavior_trainer.executor import SendInputExecutor
from starsavior_trainer.models import Action, Rect

# Win32 字面量 (故意不从被测模块导入常量 —— 模块里抄错常量时测试必须能抓到)
MOVE_ABSOLUTE = 0x0001 | 0x8000  # MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
LEFTDOWN = 0x0002
LEFTUP = 0x0004
KEYUP = 0x0002  # KEYEVENTF_KEYUP
VK_ESCAPE = 0x1B
VK_SPACE = 0x20


def absolute(pixel: int, screen_dim: int) -> int:
    """期望的 像素→绝对坐标(0-65535) 公式, 与源项目 controller.py 一致。"""
    return int(pixel * 65535 / screen_dim)


class FakeUser32:
    """Records every Win32 call the executor makes — no real mouse/keyboard.

    SendInput 收到的 INPUT 结构体在调用当下就解码成纯元组存起来,
    GetCursorPos 把预设的"点击前光标位置"写回调用方的 POINT。
    """

    def __init__(self, screen=(2000, 1000), cursor=(333, 444)) -> None:
        self.screen = screen
        self.cursor = cursor
        self.mouse_events: list[tuple[int, int, int]] = []  # (dx, dy, dwFlags)
        self.key_events: list[tuple[int, int]] = []  # (wVk, dwFlags)
        self.cursor_reads = 0

    def GetSystemMetrics(self, index):  # noqa: N802 (Win32 名)
        return self.screen[0] if index == 0 else self.screen[1]

    def GetCursorPos(self, point_ref):  # noqa: N802
        self.cursor_reads += 1
        point_ref._obj.x = self.cursor[0]
        point_ref._obj.y = self.cursor[1]
        return 1

    def SendInput(self, count, input_ref, size):  # noqa: N802
        inp = input_ref._obj
        if inp.type == 0:  # INPUT_MOUSE
            mi = inp.union.mi
            self.mouse_events.append((mi.dx, mi.dy, mi.dwFlags))
        elif inp.type == 1:  # INPUT_KEYBOARD
            ki = inp.union.ki
            self.key_events.append((ki.wVk, ki.dwFlags))
        return count


def make_executor(fake: FakeUser32) -> SendInputExecutor:
    """全部时序参数置 0, 测试瞬时跑完。"""
    return SendInputExecutor(
        user32=fake,
        move_settle=0.0,
        down_up_delay=0.0,
        repeat_interval=0.0,
        key_hold=0.0,
        key_settle=0.0,
    )


class SendInputExecutorTest(unittest.TestCase):
    # ---------- 坐标转换 ----------

    def test_pixel_to_absolute_coordinate_conversion(self) -> None:
        fake = FakeUser32(screen=(2000, 1000))
        # Rect(390, 290, 20, 20) 的中心 = (400, 300)
        result = make_executor(fake).execute(Action("click", Rect(390, 290, 20, 20), "conversion"))

        self.assertTrue(result.executed)
        self.assertEqual(result.kind, "click")
        self.assertEqual(result.point, (400, 300))
        self.assertEqual(result.reason, "conversion")
        first_move = fake.mouse_events[0]
        self.assertEqual(first_move, (absolute(400, 2000), absolute(300, 1000), MOVE_ABSOLUTE))
        # 手算值: 400*65535/2000=13107.0→13107, 300*65535/1000=19660.5→19660 (截断)
        self.assertEqual(first_move[:2], (13107, 19660))

    def test_conversion_uses_injected_screen_size(self) -> None:
        # 同一个点, 屏幕尺寸不同 → 绝对坐标必须不同 (证明真用了 GetSystemMetrics)
        fake = FakeUser32(screen=(4000, 2000))
        make_executor(fake).execute(Action("click", Rect(390, 290, 20, 20), "other screen"))

        self.assertEqual(fake.mouse_events[0][:2], (absolute(400, 4000), absolute(300, 2000)))
        self.assertEqual(fake.mouse_events[0][:2], (6553, 9830))

    # ---------- 点击序列 / 多连点 ----------

    def test_single_click_sends_move_down_up_then_restore(self) -> None:
        fake = FakeUser32(screen=(2000, 1000), cursor=(333, 444))
        make_executor(fake).execute(Action("click", Rect(390, 290, 20, 20), "tap"))

        flags = [event[2] for event in fake.mouse_events]
        self.assertEqual(flags, [MOVE_ABSOLUTE, LEFTDOWN, LEFTUP, MOVE_ABSOLUTE])
        # down/up 在当前光标位置发出: dx=dy=0 且不带 ABSOLUTE (与源项目一致)
        self.assertEqual(fake.mouse_events[1], (0, 0, LEFTDOWN))
        self.assertEqual(fake.mouse_events[2], (0, 0, LEFTUP))

    def test_repeat_click_bursts_with_move_before_each(self) -> None:
        fake = FakeUser32()
        result = make_executor(fake).execute(Action("click", Rect(390, 290, 20, 20), "burst", repeat=3))

        self.assertTrue(result.executed)
        flags = [event[2] for event in fake.mouse_events]
        self.assertEqual(flags.count(LEFTDOWN), 3)
        self.assertEqual(flags.count(LEFTUP), 3)
        # 完整序列: (move, down, up) ×3, 最后一个 move 是光标还原
        self.assertEqual(flags, [MOVE_ABSOLUTE, LEFTDOWN, LEFTUP] * 3 + [MOVE_ABSOLUTE])

    def test_repeat_zero_still_clicks_once(self) -> None:
        fake = FakeUser32()
        make_executor(fake).execute(Action("click", Rect(0, 0, 2, 2), "min once", repeat=0))

        flags = [event[2] for event in fake.mouse_events]
        self.assertEqual(flags.count(LEFTDOWN), 1)
        self.assertEqual(flags.count(LEFTUP), 1)

    # ---------- 光标保存 / 还原 ----------

    def test_cursor_saved_then_restored_to_pre_click_position(self) -> None:
        fake = FakeUser32(screen=(2000, 1000), cursor=(333, 444))
        make_executor(fake).execute(Action("click", Rect(0, 0, 10, 10), "restore me"))

        self.assertEqual(fake.cursor_reads, 1)  # GetCursorPos: 点击前保存了一次
        last = fake.mouse_events[-1]
        # 还原 = 绝对移动回 (333, 444) (源项目用 SendInput move 而非 SetCursorPos)
        self.assertEqual(last, (absolute(333, 2000), absolute(444, 1000), MOVE_ABSOLUTE))
        self.assertEqual(last[:2], (10911, 29097))

    def test_burst_restores_to_original_position_not_target(self) -> None:
        fake = FakeUser32(screen=(2000, 1000), cursor=(50, 60))
        make_executor(fake).execute(Action("click", Rect(390, 290, 20, 20), "burst", repeat=4))

        self.assertEqual(fake.cursor_reads, 1)  # 只在最开始保存一次
        self.assertEqual(fake.mouse_events[-1][:2], (absolute(50, 2000), absolute(60, 1000)))

    # ---------- 键盘 ----------

    def test_escape_key_sequence(self) -> None:
        fake = FakeUser32()
        make_executor(fake).send_escape()

        self.assertEqual(fake.key_events, [(VK_ESCAPE, 0), (VK_ESCAPE, KEYUP)])
        self.assertEqual(fake.mouse_events, [])

    def test_space_key_sequence(self) -> None:
        fake = FakeUser32()
        make_executor(fake).send_space()

        self.assertEqual(fake.key_events, [(VK_SPACE, 0), (VK_SPACE, KEYUP)])

    def test_number_keys_match_source_vk_codes(self) -> None:
        fake = FakeUser32()
        executor = make_executor(fake)
        for n in (1, 2, 3, 4):
            executor.send_number_key(n)

        expected: list[tuple[int, int]] = []
        for vk in (0x31, 0x32, 0x33, 0x34):  # VK_1..VK_4
            expected += [(vk, 0), (vk, KEYUP)]
        self.assertEqual(fake.key_events, expected)

    def test_number_key_out_of_range_is_ignored(self) -> None:
        fake = FakeUser32()
        executor = make_executor(fake)
        executor.send_number_key(0)
        executor.send_number_key(5)

        self.assertEqual(fake.key_events, [])  # 源项目行为: 非 1-4 静默忽略

    # ---------- 非点击动作 / 缺目标 ----------

    def test_move_scroll_wait_actions_are_not_executed(self) -> None:
        fake = FakeUser32()
        executor = make_executor(fake)
        for kind in ("move", "scroll", "wait"):
            result = executor.execute(Action(kind, Rect(0, 0, 10, 10), "unsupported"))
            self.assertFalse(result.executed)
            self.assertIn(kind, result.reason)

        self.assertEqual(fake.mouse_events, [])  # 一个真实事件都不许发
        self.assertEqual(fake.key_events, [])

    def test_click_without_target_is_not_executed(self) -> None:
        fake = FakeUser32()
        result = make_executor(fake).execute(Action("click", None, "no target"))

        self.assertFalse(result.executed)
        self.assertEqual(fake.mouse_events, [])

    # ---------- 非 Windows 优雅降级 ----------

    def test_init_without_windll_raises_clear_runtime_error(self) -> None:
        # 模拟非 Windows: ctypes 没有可用的 windll → 实例化必须报清晰的
        # RuntimeError (而不是 AttributeError), 且不影响注入 fake 的用法。
        with mock.patch.object(executor_module.ctypes, "windll", None):
            with self.assertRaises(RuntimeError) as ctx:
                SendInputExecutor()
        self.assertIn("Windows", str(ctx.exception))

        # 同样的环境下, 注入 fake user32 依然可用 (测试路径不依赖平台)
        with mock.patch.object(executor_module.ctypes, "windll", None):
            fake = FakeUser32()
            result = make_executor(fake).execute(Action("click", Rect(0, 0, 2, 2), "fake ok"))
        self.assertTrue(result.executed)


if __name__ == "__main__":
    unittest.main()
