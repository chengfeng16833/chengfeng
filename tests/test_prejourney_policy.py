# -*- coding: utf-8 -*-
"""赛前流程(主界面→进旅途)测试 — 迁移计划 Phase 2。

流程知识来源: docs/prejourney-flow.md(整理自用户 docx)。
画面对应: 主界面/菜单栏=新画面; 难度=INITIAL 增强; 职业筛选=CHARACTER_SELECT 增强;
刻印=BLESSING_* 增强; 卡组/好友卡=JOURNEY_START 增强。
"""

import unittest

from starsavior_trainer.classifier import (
    _has_main_menu_panel_signature,
    _has_main_screen_signature,
)
from starsavior_trainer.models import (
    GameState,
    MainMenuPanel,
    MainScreen,
    Observation,
    Rect,
    Screen,
)
from starsavior_trainer.policy import TrainerPolicy
from starsavior_trainer.prejourney import (
    imprint_index_to_row_col,
    normalize_difficulty,
)
from starsavior_trainer.regions import RegionProfile
from starsavior_trainer.run_config import PreJourneyConfig
from starsavior_trainer.screen_reader import (
    RegionText,
    parse_main_menu_panel,
    parse_main_screen,
)


def _profile(**extra: tuple[int, int, int, int]) -> RegionProfile:
    regions = {
        "main_screen_menu_button": Rect(2492, 24, 56, 56),
        "main_menu_panel_journey_entry": Rect(2120, 430, 170, 140),
    }
    for name, (x, y, w, h) in extra.items():
        regions[name] = Rect(x, y, w, h)
    return RegionProfile(name="test", resolution=(2560, 1440), regions=regions)


def _state(**prejourney_kwargs) -> GameState:
    if prejourney_kwargs:
        return GameState(prejourney=PreJourneyConfig(**prejourney_kwargs))
    return GameState(prejourney=PreJourneyConfig())


class MainScreenTest(unittest.TestCase):
    """主界面: 右上菜单按钮(有无红色感叹号都一样)→ 点开菜单栏。"""

    def test_main_screen_clicks_menu_button(self) -> None:
        payload = MainScreen(menu_button=Rect(2492, 24, 56, 56))
        action = TrainerPolicy().decide(
            _state(), Observation(Screen.MAIN_SCREEN, 0.95, payload=payload)
        )
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(2492, 24, 56, 56))

    def test_main_screen_signature_needs_two_menu_words(self) -> None:
        # 左侧竖排菜单至少命中 2 个词才算主界面, 防止单词误判。
        self.assertTrue(
            _has_main_screen_signature({"main_screen_menu_column": "战斗 管理 总部 公会 商店 观测"})
        )
        self.assertTrue(
            _has_main_screen_signature({"main_screen_menu_column": "战斗…公会"})
        )
        self.assertFalse(
            _has_main_screen_signature({"main_screen_menu_column": "商店"})
        )
        self.assertFalse(_has_main_screen_signature({}))

    def test_parse_main_screen_uses_profile_rect(self) -> None:
        payload = parse_main_screen([], _profile())
        self.assertIsNotNone(payload)
        self.assertEqual(payload.menu_button, Rect(2492, 24, 56, 56))


class MainMenuPanelTest(unittest.TestCase):
    """菜单栏面板: 点「旅程」入口。"""

    def test_main_menu_panel_clicks_journey_entry(self) -> None:
        payload = MainMenuPanel(journey_entry=Rect(2120, 430, 170, 140))
        action = TrainerPolicy().decide(
            _state(), Observation(Screen.MAIN_MENU_PANEL, 0.95, payload=payload)
        )
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(2120, 430, 170, 140))

    def test_main_menu_panel_signature(self) -> None:
        # 锚: 「旅程」+ 任一商店/作战词。区别于误触弹窗 GAME_MENU(菜单+观测)。
        self.assertTrue(
            _has_main_menu_panel_signature(
                {"main_menu_panel_grid_text": "付费商店 主线商店 作战 旅程"}
            )
        )
        self.assertFalse(
            _has_main_menu_panel_signature({"main_menu_panel_grid_text": "旅程"})
        )
        self.assertFalse(
            _has_main_menu_panel_signature({"main_menu_panel_grid_text": "菜单 观测"})
        )

    def test_parse_main_menu_panel_uses_profile_rect(self) -> None:
        payload = parse_main_menu_panel([], _profile())
        self.assertIsNotNone(payload)
        self.assertEqual(payload.journey_entry, Rect(2120, 430, 170, 140))


class InitialDifficultyTest(unittest.TestCase):
    """难度选择 = 现有「选择旅程」INITIAL 画面增强。"""

    def test_difficulty_clicked_before_start(self) -> None:
        # 配置了难度 → 第一帧点难度按钮, 第二帧点开始。
        policy = TrainerPolicy()
        state = _state(difficulty="困难")

        first = policy.decide(state, Observation(Screen.INITIAL, 0.95))
        self.assertEqual(first.kind, "click")
        self.assertEqual(first.target, Rect(2354, 1228, 155, 66))  # 困难按钮
        self.assertIn("difficulty", first.reason)

        second = policy.decide(state, Observation(Screen.INITIAL, 0.95))
        self.assertEqual(second.target, Rect(2040, 1318, 470, 75))  # 开始按钮

    def test_difficulty_accepts_english_and_chinese(self) -> None:
        self.assertEqual(normalize_difficulty("困难"), "hard")
        self.assertEqual(normalize_difficulty("hard"), "hard")
        self.assertEqual(normalize_difficulty("简单"), "easy")
        self.assertEqual(normalize_difficulty("一般"), "normal")
        self.assertEqual(normalize_difficulty("default"), "default")
        self.assertEqual(normalize_difficulty(""), "default")
        # 未知文本不点难度(当 default 处理), 不要乱点。
        self.assertEqual(normalize_difficulty("地狱"), "default")

    def test_default_difficulty_clicks_start_directly(self) -> None:
        action = TrainerPolicy().decide(_state(), Observation(Screen.INITIAL, 0.95))
        self.assertEqual(action.target, Rect(2040, 1318, 470, 75))

    def test_no_prejourney_config_keeps_old_behaviour(self) -> None:
        # 不带 prejourney 的旧调用方式行为完全不变(回归)。
        action = TrainerPolicy().decide(GameState(), Observation(Screen.INITIAL, 0.95))
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(2040, 1318, 470, 75))


class ImprintIndexTest(unittest.TestCase):
    """刻印序号 → 行列换算(网格每排 5 个)。迁移计划指定用例。"""

    def test_index_4_is_row_1_col_4(self) -> None:
        self.assertEqual(imprint_index_to_row_col(4), (1, 4))

    def test_index_12_is_row_3_col_2(self) -> None:
        self.assertEqual(imprint_index_to_row_col(12), (3, 2))

    def test_index_1_is_row_1_col_1(self) -> None:
        self.assertEqual(imprint_index_to_row_col(1), (1, 1))

    def test_index_5_and_6_wrap(self) -> None:
        self.assertEqual(imprint_index_to_row_col(5), (1, 5))
        self.assertEqual(imprint_index_to_row_col(6), (2, 1))

    def test_invalid_index_clamps_to_first(self) -> None:
        self.assertEqual(imprint_index_to_row_col(0), (1, 1))
        self.assertEqual(imprint_index_to_row_col(-3), (1, 1))


if __name__ == "__main__":
    unittest.main()
