import unittest

from starsavior_trainer.commission_inspector import CommissionInspector
from starsavior_trainer.models import (
    CommissionChoice,
    CommissionOption,
    GameState,
    Rect,
)

_ACCEPT = Rect(1880, 1255, 600, 100)
_TARGETS = [Rect(2050, 465, 380, 110), Rect(2050, 640, 380, 110), Rect(2050, 815, 380, 110)]
_TIERS = ["低阶委托", "中阶委托", "高阶委托"]


def _choice(suggested: int | None = None, char_rank: int | None = 21) -> CommissionChoice:
    """3-tier commission list; only the currently-selected one shows its 建议综合等级."""
    options = [
        CommissionOption(name="史莱姆讨伐委托", rank=_TIERS[i], has_red_text=False, target=_TARGETS[i])
        for i in range(3)
    ]
    return CommissionChoice(
        options=options,
        accept_button=_ACCEPT,
        selected_suggested_rank=suggested,
        character_rank=char_rank,
    )


class CommissionInspectorTest(unittest.TestCase):
    def test_inspects_each_then_accepts_highest_doable_tier(self) -> None:
        # Suggested ranks: 低=17, 中=21, 高=25; character rank 21 → highest doable is
        # the 中阶 (21 ≤ 21), NOT 低阶 (the bug) nor 高阶 (25 > 21, can't do).
        insp = CommissionInspector()
        st = GameState()

        a = insp.decide(_choice(suggested=None), st)   # nothing recorded → inspect 低阶
        self.assertEqual(a.target, _TARGETS[0])

        a = insp.decide(_choice(suggested=17), st)     # record 低=17 → inspect 中阶
        self.assertEqual(a.target, _TARGETS[1])

        a = insp.decide(_choice(suggested=21), st)     # record 中=21 → inspect 高阶
        self.assertEqual(a.target, _TARGETS[2])

        a = insp.decide(_choice(suggested=25), st)     # record 高=25; pick 中阶, select it
        self.assertEqual(a.target, _TARGETS[1])
        self.assertIn("中阶", a.reason)

        a = insp.decide(_choice(suggested=21), st)     # 中阶 already selected → accept
        self.assertEqual(a.target, _ACCEPT)
        self.assertIn("accept", a.reason)

    def test_picks_high_tier_when_character_rank_allows(self) -> None:
        # Same suggested ranks but a strong character (rank 30) → take 高阶 (25 ≤ 30).
        insp = CommissionInspector()
        st = GameState()
        insp.decide(_choice(suggested=None, char_rank=30), st)
        insp.decide(_choice(suggested=17, char_rank=30), st)
        insp.decide(_choice(suggested=21, char_rank=30), st)
        # All read; 高阶 is both the best pick AND the one just inspected (selected),
        # so it accepts directly — no extra re-select step.
        a = insp.decide(_choice(suggested=25, char_rank=30), st)
        self.assertEqual(a.target, _ACCEPT)
        self.assertIn("高阶", a.reason)
        self.assertIn("accept", a.reason)

    def test_accepts_commission_up_to_3_levels_above_rank(self) -> None:
        # User rule: a commission may be up to 3 levels ABOVE the character rank and
        # still be taken; only >3 above is "too hard → pick another". Character 21,
        # suggested 低=17/中=23/高=26: 中 (23 ≤ 21+3=24) is doable, 高 (26 > 24) is
        # not → pick the 中阶, not the 低阶.
        insp = CommissionInspector()
        st = GameState()
        insp.decide(_choice(suggested=None, char_rank=21), st)   # inspect 低
        insp.decide(_choice(suggested=17, char_rank=21), st)     # 低=17 → inspect 中
        insp.decide(_choice(suggested=23, char_rank=21), st)     # 中=23 → inspect 高
        a = insp.decide(_choice(suggested=26, char_rank=21), st)  # 高=26 > 24 → pick 中阶
        self.assertEqual(a.target, _TARGETS[1])
        self.assertIn("中阶", a.reason)

    def test_rejects_commission_more_than_3_levels_above_rank(self) -> None:
        # Character 21, suggested 低=17/中=25/高=28: both 中 (25) and 高 (28) are >24,
        # so only 低 (17) is within tolerance → pick 低阶 (the conservative fallback,
        # not a too-hard commission that would likely fail).
        insp = CommissionInspector()
        st = GameState()
        insp.decide(_choice(suggested=None, char_rank=21), st)
        insp.decide(_choice(suggested=17, char_rank=21), st)
        insp.decide(_choice(suggested=25, char_rank=21), st)
        a = insp.decide(_choice(suggested=28, char_rank=21), st)  # all read; only 低 doable
        self.assertEqual(a.target, _TARGETS[0])
        self.assertIn("低阶", a.reason)

    def test_unknown_character_rank_defers_to_policy(self) -> None:
        # Without a character rank we can't judge doability — return None so the
        # policy's conservative fallback handles it (no crash, no wrong pick).
        insp = CommissionInspector()
        self.assertIsNone(insp.decide(_choice(suggested=None, char_rank=None), GameState()))

    def test_single_option_defers_to_policy(self) -> None:
        insp = CommissionInspector()
        one = CommissionChoice(
            options=[CommissionOption("史莱姆讨伐委托", "低阶委托", False, _TARGETS[0])],
            accept_button=_ACCEPT,
            character_rank=21,
        )
        self.assertIsNone(insp.decide(one, GameState()))


if __name__ == "__main__":
    unittest.main()
