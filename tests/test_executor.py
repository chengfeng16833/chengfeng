import sys
import types
import unittest

from starsavior_trainer.executor import DryRunExecutor, PyAutoGuiExecutor, map_action_to_rect
from starsavior_trainer.models import Action, Rect


class _FakePyAutoGui:
    """Records clicks/moves so we can assert burst behaviour without a real mouse."""

    def __init__(self) -> None:
        self.clicks = 0
        self.moves: list[tuple[int, int]] = []

    def moveTo(self, x, y, duration=0.0) -> None:  # noqa: N802 (pyautogui name)
        self.moves.append((x, y))

    def click(self) -> None:
        self.clicks += 1


class ExecutorTest(unittest.TestCase):
    def test_dry_run_reports_click_center_without_executing(self) -> None:
        action = Action("click", Rect(10, 20, 30, 40), "test click")

        result = DryRunExecutor().execute(action)

        self.assertFalse(result.executed)
        self.assertEqual(result.point, (25, 40))
        self.assertIn("dry run", result.reason)

    def test_map_action_to_rect_scales_and_offsets_target(self) -> None:
        action = Action("click", Rect(1000, 700, 200, 100), "test click")

        mapped = map_action_to_rect(action, (2000, 1000), Rect(50, 100, 1000, 500))

        self.assertEqual(mapped.target, Rect(550, 450, 100, 50))
        self.assertEqual(mapped.reason, action.reason)

    def test_map_action_to_rect_preserves_repeat(self) -> None:
        action = Action("click", Rect(1000, 700, 200, 100), "burst", repeat=4)

        mapped = map_action_to_rect(action, (2000, 1000), Rect(50, 100, 1000, 500))

        self.assertEqual(mapped.repeat, 4)

    def _executor_with_fake(self) -> tuple[PyAutoGuiExecutor, _FakePyAutoGui]:
        fake = _FakePyAutoGui()
        # PyAutoGuiExecutor imports pyautogui in __init__; inject a stub module so
        # the test runs without a real display/mouse.
        sys.modules["pyautogui"] = types.SimpleNamespace(  # type: ignore[assignment]
            moveTo=fake.moveTo, click=fake.click
        )
        try:
            executor = PyAutoGuiExecutor()
        finally:
            del sys.modules["pyautogui"]
        executor._pyautogui = fake
        return executor, fake

    def test_single_click_executes_once(self) -> None:
        executor, fake = self._executor_with_fake()

        result = executor.execute(Action("click", Rect(10, 20, 4, 4), "tap"))

        self.assertTrue(result.executed)
        self.assertEqual(fake.clicks, 1)

    def test_repeat_click_bursts(self) -> None:
        executor, fake = self._executor_with_fake()

        result = executor.execute(Action("click", Rect(10, 20, 4, 4), "burst", repeat=4))

        self.assertTrue(result.executed)
        self.assertEqual(fake.clicks, 4)


if __name__ == "__main__":
    unittest.main()
