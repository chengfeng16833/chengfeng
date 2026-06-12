# -*- coding: utf-8 -*-
"""前期训练策略(2026-06-12 用户两次拍板的最终版)。

优先级: 主属性彩圈 > 韧性彩圈 > 人头≥4刷好感(任意属性) > 主属性普通训练保底。
训练是主业, 支援卡人头不得压过彩圈; 人头<4 不值得为好感跑别的属性。
"""

import unittest

from starsavior_trainer.models import GameState, Rect, TrainingChoice
from starsavior_trainer.policy import TrainerPolicy


def _choice(
    attr: str, icons: int = 0, *, selected: bool = False, fail: int | None = None, ring: str = "none"
) -> TrainingChoice:
    order = ("power", "stamina", "guts", "wisdom", "speed")
    y = 338 + order.index(attr) * 150
    return TrainingChoice(
        name=f"{attr}训练",
        stat_gain=0,
        ring=ring,
        fail_rate=fail,
        target=Rect(1750, y, 650, 112),
        attr=attr,
        icon_count=icons,
        selected=selected,
        confirm_button=Rect(2080, 1252, 400, 95),
    )


class EarlyPriorityTest(unittest.TestCase):
    """优先级分层: 彩圈 > 大人头 > 保底。"""

    def test_primary_ring_beats_everything(self) -> None:
        # 力量出彩圈 → 必选, 哪怕体力挂着 8 个人头。
        policy = TrainerPolicy()
        choices = [_choice("power", 0, ring="blue"), _choice("stamina", 8), _choice("guts", 5)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, _choice("power").target)

    def test_guts_ring_is_second(self) -> None:
        # 没有主属性彩圈时, 韧性彩圈压过任何人头。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("guts", 0, ring="gold"), _choice("stamina", 8)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, _choice("guts").target)

    def test_other_attr_ring_does_not_jump_queue(self) -> None:
        # 体力出彩圈(非主非韧)不享受彩圈层加分 → 主属性保底胜。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 0, ring="rainbow")]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, _choice("power").target)

    def test_big_icons_pull_training_for_bond(self) -> None:
        # 无彩圈, 体力 5 人头(≥4, 刷好感值得跑) → 压过主属性保底。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 5), _choice("guts", 1)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, _choice("stamina").target)

    def test_small_icons_do_not_count(self) -> None:
        # 人头 ≤3 不计分(不值得为好感跑别的属性)→ 主属性保底胜。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 3), _choice("guts", 2)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, _choice("power").target)

    def test_fallback_primary_when_nothing_special(self) -> None:
        # 什么信号都没有 → 主属性普通训练保底(训练是主业, 回合不空过)。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 0), _choice("guts", 0)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, _choice("power").target)


class EarlyTwoStepAndFailTest(unittest.TestCase):
    def test_selected_with_ok_fail_rate_confirms(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 0, selected=True, fail=10, ring="blue"), _choice("guts", 1)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, Rect(2080, 1252, 400, 95))
        self.assertIn("confirm training", action.reason)  # CSV 钩子依赖这个字样

    def test_high_fail_rate_rejects_and_falls_to_next(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 0, selected=True, fail=45, ring="blue"), _choice("guts", 2)]
        first = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(first.kind, "pause")
        second = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertEqual(second.target, _choice("guts", 2).target)

    def test_all_rejected_falls_back_to_none(self) -> None:
        policy = TrainerPolicy()
        policy._early_icon_rejected.update({"power", "stamina", "guts", "wisdom", "speed"})
        choices = [_choice("power", 3), _choice("guts", 2)]
        self.assertIsNone(policy.decide_training_early_icons(choices, GameState()))


class StaminaBuildTest(unittest.TestCase):
    """体力角色: 主属性=体力(体力>韧性, 力量不再特殊)。"""

    def test_stamina_ring_first_for_stamina_build(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("stamina", 0, ring="blue"), _choice("power", 8), _choice("guts", 0, ring="gold")]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="stamina_tank"))
        self.assertEqual(action.target, _choice("stamina").target)

    def test_stamina_fallback_when_nothing_special(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 2), _choice("stamina", 1), _choice("guts", 0)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="stamina_tank"))
        self.assertEqual(action.target, _choice("stamina", 1).target)


class EarlyScoreFormulaTest(unittest.TestCase):
    """量化分公式: 主彩圈10000 / 韧彩圈5000 / 人头≥4 时 x50 / 底分10与5。"""

    def test_score_layers(self) -> None:
        policy = TrainerPolicy()
        self.assertEqual(policy.early_training_score(_choice("power", 0, ring="blue"), "power"), 10010)
        self.assertEqual(policy.early_training_score(_choice("guts", 0, ring="gold"), "power"), 5005)
        self.assertEqual(policy.early_training_score(_choice("stamina", 5), "power"), 250)
        self.assertEqual(policy.early_training_score(_choice("stamina", 3), "power"), 0)
        self.assertEqual(policy.early_training_score(_choice("power", 0), "power"), 10)
        self.assertEqual(policy.early_training_score(_choice("guts", 0), "power"), 5)

    def test_reason_contains_score_breakdown(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 0, ring="blue"), _choice("guts", 1)]
        action = policy.decide_training_early_icons(choices, GameState(build_profile="power_focus"))
        self.assertIn("power=10010", action.reason)


if __name__ == "__main__":
    unittest.main()
