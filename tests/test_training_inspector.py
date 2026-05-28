import unittest

from starsavior_trainer.models import GameState, Rect, TrainingChoice
from starsavior_trainer.training_inspector import TrainingInspector

_CONFIRM = Rect(2080, 1252, 400, 95)
_TARGETS = {
    "power": Rect(1750, 338, 650, 112),
    "stamina": Rect(1750, 487, 650, 112),
    "guts": Rect(1750, 635, 650, 112),
}


def _choices(selected: str | None = None, gain: int = 0, fail: int = 0) -> list[TrainingChoice]:
    """Three priority trainings; only `selected` shows its +N gain and 失败率."""
    out = []
    for name in ("power", "stamina", "guts"):
        is_sel = name == selected
        out.append(
            TrainingChoice(
                name=name,
                stat_gain=gain if is_sel else 0,
                ring="none",
                fail_rate=fail if is_sel else 0,
                target=_TARGETS[name],
                selected=is_sel,
                confirm_button=_CONFIRM,
            )
        )
    return out


class TrainingInspectorTest(unittest.TestCase):
    def test_inspects_each_then_confirms_highest_gain(self) -> None:
        insp = TrainingInspector()
        st = GameState(build_profile="power_focus")

        a = insp.decide(_choices(), st)  # nothing selected -> inspect power
        self.assertEqual(a.kind, "click")
        self.assertEqual(a.target, _TARGETS["power"])

        a = insp.decide(_choices("power", gain=21), st)  # record power=21 -> inspect stamina
        self.assertEqual(a.target, _TARGETS["stamina"])

        a = insp.decide(_choices("stamina", gain=18), st)  # record stamina=18 -> inspect guts
        self.assertEqual(a.target, _TARGETS["guts"])

        # record guts=25; guts is the highest AND already selected -> confirm.
        a = insp.decide(_choices("guts", gain=25), st)
        self.assertEqual(a.target, _CONFIRM)
        self.assertIn("confirm training guts", a.reason)

    def test_reselects_winner_when_it_is_not_the_last_inspected(self) -> None:
        insp = TrainingInspector()
        st = GameState(build_profile="power_focus")

        insp.decide(_choices(), st)                       # inspect power
        insp.decide(_choices("power", gain=25), st)       # power=25, inspect stamina
        insp.decide(_choices("stamina", gain=18), st)     # stamina=18, inspect guts
        a = insp.decide(_choices("guts", gain=12), st)    # guts=12; best=power -> select power
        self.assertEqual(a.target, _TARGETS["power"])
        self.assertIn("choose training power", a.reason)

        a = insp.decide(_choices("power", gain=25), st)   # power selected -> confirm
        self.assertEqual(a.target, _CONFIRM)
        self.assertIn("confirm training power", a.reason)

    def test_defers_to_policy_when_all_priority_trainings_too_risky(self) -> None:
        insp = TrainingInspector(max_fail_rate=30)
        st = GameState(build_profile="power_focus")

        insp.decide(_choices(), st)
        insp.decide(_choices("power", gain=21, fail=55), st)
        insp.decide(_choices("stamina", gain=18, fail=55), st)
        # All inspected, all fail rates exceed the threshold -> return None so the
        # policy can route back to the hub to rest.
        self.assertIsNone(insp.decide(_choices("guts", gain=25, fail=55), st))


if __name__ == "__main__":
    unittest.main()
