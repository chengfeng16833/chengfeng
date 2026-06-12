# -*- coding: utf-8 -*-
"""量化训练策略(2026-06-12 用户拍板, 同日实跑后修订): 按回合分段。

≤16回合(跑好感期): 支援卡随机分布在 5 个训练 → 5 个全检视全参与,
人头最多者胜(1个也算), 平手 主属性>韧性>其他, 没人头主属性保底。
>16回合(收获期): 好感跑满开始出彩圈 → 主属性彩圈 > 韧性彩圈 >
人头≥4(没跑满的尾巴) > 主属性保底; 非主非韧的彩圈不跳队。
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
        back_button=Rect(60, 50, 90, 80),
    )


def _early_state(build: str = "power_focus") -> GameState:
    return GameState(build_profile=build, current_round=5)


def _late_state(build: str = "power_focus") -> GameState:
    return GameState(build_profile=build, current_round=20)


class IconPollingTest(unittest.TestCase):
    """人头列只显示选中卡 → 前期轮询候选: 逐个点过去读数, 读全才打分。"""

    def test_polls_unseen_candidates_first(self) -> None:
        policy = TrainerPolicy()
        # 全部未知(-1): 先点主属性卡读它的人头。
        choices = [_choice("power", -1), _choice("stamina", -1), _choice("guts", -1)]
        a1 = policy.decide_training_quantified(choices, _early_state())
        self.assertIn("inspect support icons of power", a1.reason)

        # 力量选中读到 2 个头 → 下一步点韧性去读。
        choices2 = [_choice("power", 2, selected=True, fail=5), _choice("guts", -1)]
        a2 = policy.decide_training_quantified(choices2, _early_state())
        self.assertIn("inspect support icons of guts", a2.reason)

        # 韧性选中读到 3 个头 → 候选读全, 韧性人头多 → 选韧性。
        choices3 = [_choice("power", -1), _choice("guts", 3, selected=True, fail=5)]
        a3 = policy.decide_training_quantified(choices3, _early_state())
        self.assertIn("confirm training guts", a3.reason)

    def test_seen_resets_via_clear(self) -> None:
        policy = TrainerPolicy()
        policy._early_icons_seen.update({"power": 2, "guts": 1})
        policy._early_icons_seen.clear()  # live_loop 在离开训练画面时调用
        choices = [_choice("power", -1), _choice("guts", -1)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertIn("inspect", action.reason)


class EarlyPhaseTest(unittest.TestCase):
    """≤16回合: 跑好感, 5 训练全参与, 人头最多者胜。"""

    def test_most_icons_wins_across_all_five(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 1), _choice("stamina", 8), _choice("guts", 3)]
        action = policy.decide_training_quantified(choices, _early_state())
        # 实跑后改拍板: 人头最多者胜, 不限属性 —— 体力8人头 > 韧性3 > 力量1。
        self.assertEqual(action.target, _choice("stamina").target)

    def test_one_icon_already_counts_in_early(self) -> None:
        # 前期 1 个人头也值得跟(跑好感是主任务, 没有≥4门槛)。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("guts", 1)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertEqual(action.target, _choice("guts").target)

    def test_tie_prefers_primary(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 2), _choice("guts", 2)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertEqual(action.target, _choice("power").target)

    def test_no_icons_falls_back_to_primary(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 0), _choice("guts", 0)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertEqual(action.target, _choice("power").target)

    def test_unknown_round_treated_as_early(self) -> None:
        # 回合未知(读不出大厅日期)→ 保守按前期跑好感。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("guts", 2)]
        action = policy.decide_training_quantified(choices, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, _choice("guts").target)

    def test_stamina_build_follows_icons_too(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 8), _choice("stamina", 1), _choice("guts", 0)]
        action = policy.decide_training_quantified(choices, _early_state("stamina_tank"))
        # 好感是全局资源: 体力角色见力量8人头也跟着跑(8x50 > 1x50+主属性底分10)。
        self.assertEqual(action.target, _choice("power").target)


class LatePhaseTest(unittest.TestCase):
    """>12回合: 收彩圈。主属性彩圈 > 韧性彩圈 > 人头≥4 > 主属性保底。"""

    def test_primary_ring_beats_everything(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 0, ring="blue"), _choice("stamina", 8), _choice("guts", 5)]
        action = policy.decide_training_quantified(choices, _late_state())
        self.assertEqual(action.target, _choice("power").target)

    def test_guts_ring_is_second(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("guts", 0, ring="gold"), _choice("stamina", 8)]
        action = policy.decide_training_quantified(choices, _late_state())
        self.assertEqual(action.target, _choice("guts").target)

    def test_other_attr_ring_does_not_jump_queue(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 0, ring="rainbow")]
        action = policy.decide_training_quantified(choices, _late_state())
        self.assertEqual(action.target, _choice("power").target)

    def test_big_icons_pull_for_unfinished_bond(self) -> None:
        # 无彩圈, 体力5人头(好感尾巴) → 值得跑。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 5), _choice("guts", 1)]
        action = policy.decide_training_quantified(choices, _late_state())
        self.assertEqual(action.target, _choice("stamina").target)

    def test_small_icons_do_not_count_late(self) -> None:
        # 后期人头≤3不计(用户原话: 超过3个才选) → 主属性保底。
        policy = TrainerPolicy()
        choices = [_choice("power", 0), _choice("stamina", 3)]
        action = policy.decide_training_quantified(choices, _late_state())
        self.assertEqual(action.target, _choice("power").target)


class TwoStepAndFailTest(unittest.TestCase):
    def test_selected_with_ok_fail_rate_confirms(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 2, selected=True, fail=10), _choice("guts", 1)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertEqual(action.target, Rect(2080, 1252, 400, 95))
        self.assertIn("confirm training", action.reason)  # CSV 钩子依赖这个字样

    def test_high_fail_rate_goes_straight_to_rest(self) -> None:
        # 失败率全训练通用(疲劳决定): 一张卡读到45% = 全部45%, 换训练无意义
        # → 直接点返回回大厅 + 标记 _needs_rest(大厅会去休息)。
        policy = TrainerPolicy()
        choices = [_choice("power", 2, selected=True, fail=45), _choice("guts", 1)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(60, 50, 90, 80))  # back_button
        self.assertIn("rest", action.reason)
        self.assertTrue(policy._needs_rest)

    def test_universal_fail_rate_read_from_any_card(self) -> None:
        # 哪怕显示失败率的不是最优卡(韧性选中45%), 也直接休息——通用失败率。
        policy = TrainerPolicy()
        choices = [_choice("power", 5), _choice("guts", 0, selected=True, fail=45)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertEqual(action.target, Rect(60, 50, 90, 80))
        self.assertTrue(policy._needs_rest)


class ScoreFormulaTest(unittest.TestCase):
    def test_early_formula(self) -> None:
        policy = TrainerPolicy()
        self.assertEqual(policy.early_training_score(_choice("power", 2), "power"), 10 + 100)
        self.assertEqual(policy.early_training_score(_choice("guts", 1), "power"), 5 + 50)
        # 非主非韧: 没底分但人头照算(实跑后改拍板, 5 训练全参与)。
        self.assertEqual(policy.early_training_score(_choice("stamina", 8), "power"), 400)
        # 前期万一出彩圈: ring_bonus(≤40)只作平手加分, 压不过 1 个人头(50)。
        self.assertEqual(policy.early_training_score(_choice("power", 0, ring="rainbow"), "power"), 50)

    def test_late_formula(self) -> None:
        policy = TrainerPolicy()
        self.assertEqual(policy.late_training_score(_choice("power", 0, ring="blue"), "power"), 10010)
        self.assertEqual(policy.late_training_score(_choice("guts", 0, ring="gold"), "power"), 5005)
        self.assertEqual(policy.late_training_score(_choice("stamina", 5), "power"), 250)
        self.assertEqual(policy.late_training_score(_choice("stamina", 3), "power"), 0)
        self.assertEqual(policy.late_training_score(_choice("power", 0), "power"), 10)

    def test_reason_contains_breakdown(self) -> None:
        policy = TrainerPolicy()
        choices = [_choice("power", 3), _choice("guts", 1)]
        action = policy.decide_training_quantified(choices, _early_state())
        self.assertIn("power=160", action.reason)


if __name__ == "__main__":
    unittest.main()
