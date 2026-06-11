import unittest

from starsavior_trainer.cli.live_loop import state_for_skill_learning
from starsavior_trainer.models import GameState, Observation, Screen
from starsavior_trainer.policy import TrainerPolicy


class LiveLoopStateTests(unittest.TestCase):
    def test_allows_skill_learning_on_skill_screen_after_dday_trading(self) -> None:
        policy = TrainerPolicy()
        policy._dday_trading_done = True

        state = state_for_skill_learning(
            GameState(allow_skill_learning=False),
            Observation(Screen.SKILL_SELECT, 0.95, payload=[]),
            policy,
        )

        self.assertTrue(state.allow_skill_learning)

    def test_keeps_skill_learning_disabled_without_dday_trading(self) -> None:
        state = state_for_skill_learning(
            GameState(allow_skill_learning=False),
            Observation(Screen.SKILL_SELECT, 0.95, payload=[]),
            TrainerPolicy(),
        )

        self.assertFalse(state.allow_skill_learning)

    def test_resets_skill_learning_when_returning_to_hub(self) -> None:
        state = state_for_skill_learning(
            GameState(allow_skill_learning=True),
            Observation(Screen.TRAINING_HUB, 0.95, payload=None),
            TrainerPolicy(),
        )

        self.assertFalse(state.allow_skill_learning)


if __name__ == "__main__":
    unittest.main()
