# -*- coding: utf-8 -*-
"""前期人头优先训练策略(2026-06-12 用户拍板)。

力量系: 前12回合在 力量/韧性 中选支援卡人头最多的(刷好感), 不逐卡检视;
人头检测不可用/候选全排除 → 返回 None 交回检视器老逻辑。
"""

import unittest

from starsavior_trainer.models import GameState, Rect, TrainingChoice
from starsavior_trainer.policy import TrainerPolicy


def _choice(attr: str, icons: int, *, selected: bool = False, fail: int | None = None) -> TrainingChoice:
    order = ("power", "stamina", "guts", "wisdom", "speed")
    y = 338 + order.index(attr) * 150
    return TrainingChoice(
        name=f"{attr}训练",
        stat_gain=0,
        ring="none",
        fail_rate=fail,
        target=Rect(1750, y, 650, 112),
        attr=attr,
        icon_count=icons,
        selected=selected,
        confirm_button=Rect(2080, 1252, 400, 95),
    )


class EarlyIconTrainingTest(unittest.TestCase):
    def test_most_icons_wins_within_power_guts(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 2), _choice("stamina", 5), _choice("guts", 4)]
        action = policy.decide_training_early_icons(choices, GameState())
        # 体力人头再多也不选(不在 力量/韧性 候选里); 韧性4 > 力量2。
        self.assertEqual(action.target, _choice("guts", 4).target)
        self.assertIn("guts", action.reason)

    def test_tie_prefers_power(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 3), _choice("guts", 3)]
        action = policy.decide_training_early_icons(choices, GameState())
        self.assertEqual(action.target, _choice("power", 3).target)

    def test_selected_with_ok_fail_rate_confirms(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 3, selected=True, fail=10), _choice("guts", 1)]
        action = policy.decide_training_early_icons(choices, GameState())
        self.assertEqual(action.target, Rect(2080, 1252, 400, 95))
        self.assertIn("confirm training", action.reason)  # CSV 钩子依赖这个字样

    def test_high_fail_rate_rejects_and_falls_to_next(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 5, selected=True, fail=45), _choice("guts", 2)]
        first = policy.decide_training_early_icons(choices, GameState())
        self.assertEqual(first.kind, "pause")
        # 下一帧: 力量已排除 → 选韧性。
        choices2 = [_choice("power", 5, selected=True, fail=45), _choice("guts", 2)]
        second = policy.decide_training_early_icons(choices2, GameState())
        self.assertEqual(second.target, _choice("guts", 2).target)

    def test_all_zero_icons_falls_back_to_none(self) -> None:
        # 人头区域未校准(全0)→ None, live_loop 回退检视器老逻辑。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("guts", 0)]
        self.assertIsNone(policy.decide_training_early_icons(choices, GameState()))

    def test_both_rejected_falls_back_to_none(self) -> None:
        policy = TrainerPolicy()
        policy._early_icon_rejected.update({"power", "guts"})
        choices = [_choice("power", 3), _choice("guts", 2)]
        self.assertIsNone(policy.decide_training_early_icons(choices, GameState()))


if __name__ == "__main__":
    unittest.main()
