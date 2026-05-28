import unittest

from starsavior_trainer.blessing_inspector import BlessingChoiceInspector
from starsavior_trainer.models import BlessingChoice, BlessingOption, GameState, Rect


class BlessingChoiceInspectorTest(unittest.TestCase):
    def _choice_factory(self, card_1: Rect, card_2: Rect, confirm: Rect):
        def choice(detail_sub: int) -> BlessingChoice:
            return BlessingChoice(
                [
                    BlessingOption("power_45_01", "power", 45, card_1),
                    BlessingOption("power_45_02", "power", 45, card_2),
                ],
                confirm_button=confirm,
                detail_sub_blessing_count=detail_sub,
            )

        return choice

    def test_inspects_by_clicking_each_candidate_not_hovering(self) -> None:
        # Hovering never refreshed the detail panel (sub count read 0 for all),
        # so the inspector must CLICK each candidate to select+read it.
        inspector = BlessingChoiceInspector({"power_focus": "power"})
        confirm = Rect(300, 300, 80, 40)
        card_1, card_2 = Rect(10, 10, 20, 20), Rect(40, 10, 20, 20)
        choice = self._choice_factory(card_1, card_2, confirm)
        state = GameState(build_profile="power_focus")

        # Inspect card_1 (click selects it; the count passed is irrelevant yet).
        action = inspector.decide(choice(0), state)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, card_1)

        # Panel now shows card_1 -> count 0 recorded for it; inspect card_2 next.
        action = inspector.decide(choice(0), state)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, card_2)
        self.assertEqual(inspector.records, {"power_45_01": 0})

        # Panel now shows card_2 -> count 2 recorded. card_2 wins AND is already
        # selected (last clicked), so confirm directly (which resets state).
        action = inspector.decide(choice(2), state)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, confirm)
        self.assertIn("sub_blessings=2", action.reason)

    def test_reselects_winner_when_it_is_not_the_last_card_inspected(self) -> None:
        # card_1 has MORE sub-blessings, but card_2 was inspected last (so it's the
        # selected one). The inspector must click card_1 to select it, then confirm
        # — without trusting the ambiguous parsed selected_name.
        inspector = BlessingChoiceInspector({"power_focus": "power"})
        confirm = Rect(300, 300, 80, 40)
        card_1, card_2 = Rect(10, 10, 20, 20), Rect(40, 10, 20, 20)
        choice = self._choice_factory(card_1, card_2, confirm)
        state = GameState(build_profile="power_focus")

        self.assertEqual(inspector.decide(choice(0), state).target, card_1)   # inspect card_1
        self.assertEqual(inspector.decide(choice(3), state).target, card_2)   # record card_1=3, inspect card_2
        # record card_2=1; best=card_1 (3>1) but card_2 is selected -> select card_1.
        action = inspector.decide(choice(1), state)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, card_1)
        self.assertIn("power_45_01", action.reason)
        self.assertEqual(inspector.records, {"power_45_01": 3, "power_45_02": 1})
        # card_1 now selected (last clicked) -> confirm.
        action = inspector.decide(choice(3), state)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, confirm)

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
