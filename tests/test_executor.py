import unittest

from starsavior_trainer.executor import DryRunExecutor, map_action_to_rect
from starsavior_trainer.models import Action, Rect


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


if __name__ == "__main__":
    unittest.main()
