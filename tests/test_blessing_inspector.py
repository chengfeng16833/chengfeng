import unittest

from starsavior_trainer.blessing_inspector import BlessingChoiceInspector
from starsavior_trainer.models import BlessingChoice, BlessingOption, GameState, Rect


class BlessingChoiceInspectorTest(unittest.TestCase):
    def test_inspects_equal_value_candidates_before_choosing_best_sub_blessing(self) -> None:
        inspector = BlessingChoiceInspector({"power_focus": "power"})
        confirm = Rect(300, 300, 80, 40)
        card_1 = Rect(10, 10, 20, 20)
        card_2 = Rect(40, 10, 20, 20)

        def choice(detail_sub: int) -> BlessingChoice:
            return BlessingChoice(
                [
                    BlessingOption("power_45_01", "power", 45, card_1),
                    BlessingOption("power_45_02", "power", 45, card_2),
                ],
                confirm_button=confirm,
                detail_sub_blessing_count=detail_sub,
            )

        state = GameState(build_profile="power_focus")

        action = inspector.decide(choice(0), state)
        self.assertEqual(action.kind, "move")
        self.assertEqual(action.target, card_1)

        action = inspector.decide(choice(0), state)
        self.assertEqual(action.kind, "move")
        self.assertEqual(action.target, card_2)

        action = inspector.decide(choice(2), state)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, card_2)
        self.assertIn("power_45_02", action.reason)
        self.assertEqual(inspector.records, {"power_45_01": 0, "power_45_02": 2})

    def test_returns_none_when_top_value_card_is_unique(self) -> None:
        inspector = BlessingChoiceInspector({"power_focus": "power"})

        action = inspector.decide(
            BlessingChoice(
                [
                    BlessingOption("power_20", "power", 20, Rect(10, 10, 20, 20)),
                    BlessingOption("power_35", "power", 35, Rect(40, 10, 20, 20)),
                ]
            ),
            GameState(build_profile="power_focus"),
        )

        self.assertIsNone(action)

    def test_lower_value_card_never_competes_even_with_more_sub_blessings(self) -> None:
        # A 35-value card must win over a 30-value card regardless of sub-blessings:
        # value is strictly primary, so the inspector should not engage (defers to policy).
        inspector = BlessingChoiceInspector({"power_focus": "power"})

        action = inspector.decide(
            BlessingChoice(
                [
                    BlessingOption("power_35", "power", 35, Rect(10, 10, 20, 20)),
                    BlessingOption("power_30", "power", 30, Rect(40, 10, 20, 20)),
                ],
                detail_sub_blessing_count=3,
            ),
            GameState(build_profile="power_focus"),
        )

        self.assertIsNone(action)


if __name__ == "__main__":
    unittest.main()
