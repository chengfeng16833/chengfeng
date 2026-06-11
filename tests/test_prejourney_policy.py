# -*- coding: utf-8 -*-
"""赛前流程(主界面→进旅途)测试 — 迁移计划 Phase 2。

流程知识来源: docs/prejourney-flow.md(整理自用户 docx)。
画面对应: 主界面/菜单栏=新画面; 难度=INITIAL 增强; 职业筛选=CHARACTER_SELECT 增强;
刻印=BLESSING_* 增强; 卡组/好友卡=JOURNEY_START 增强。
"""

import unittest

from starsavior_trainer.classifier import (
    _has_filter_dialog_signature,
    _has_main_menu_panel_signature,
    _has_main_screen_signature,
)
from starsavior_trainer.models import (
    BlessingChoice,
    CharacterOption,
    CharacterSelect,
    FilterDialog,
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
    normalize_profession,
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


def _character_select(filter_button: Rect | None = Rect(2430, 245, 85, 80)) -> CharacterSelect:
    return CharacterSelect(
        options=[
            CharacterOption(
                name="芙蕾", rank=None, stars=3, specialty=None,
                selected=False, target=Rect(2200, 300, 300, 90),
            )
        ],
        confirm_button=Rect(2280, 1300, 240, 80),
        filter_button=filter_button,
    )


class ProfessionFilterTest(unittest.TestCase):
    """角色选择的职业筛选: 漏斗按钮 → 筛选弹窗点职业 → 确认 → 回列表找角色。"""

    def test_character_select_opens_filter_when_profession_configured(self) -> None:
        policy = TrainerPolicy()
        state = _state(profession="术师")
        payload = _character_select()

        action = policy.decide(state, Observation(Screen.CHARACTER_SELECT, 0.95, payload=payload))
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(2430, 245, 85, 80))
        self.assertIn("filter", action.reason)

    def test_character_select_skips_filter_without_profession(self) -> None:
        policy = TrainerPolicy()
        state = _state()  # profession 默认 ""
        payload = _character_select()

        action = policy.decide(state, Observation(Screen.CHARACTER_SELECT, 0.95, payload=payload))
        # 不点漏斗, 走现有找角色逻辑(没配目标角色时的现有行为)。
        self.assertNotEqual(action.target, Rect(2430, 245, 85, 80))

    def test_character_select_skips_filter_after_done(self) -> None:
        policy = TrainerPolicy()
        policy.prejourney_progress.profession_filter_done = True
        state = _state(profession="术师")
        payload = _character_select()

        action = policy.decide(state, Observation(Screen.CHARACTER_SELECT, 0.95, payload=payload))
        self.assertNotEqual(action.target, Rect(2430, 245, 85, 80))

    def test_filter_dialog_clicks_profession_then_confirm(self) -> None:
        policy = TrainerPolicy()
        state = _state(profession="术师")
        payload = FilterDialog(
            profession_buttons={
                "坦克": Rect(384, 590, 250, 100),
                "术师": Rect(1248, 590, 250, 100),
            },
            confirm_button=Rect(1310, 1180, 260, 90),
        )
        obs = Observation(Screen.FILTER_DIALOG, 0.95, payload=payload)

        first = policy.decide(state, obs)
        self.assertEqual(first.target, Rect(1248, 590, 250, 100))

        second = policy.decide(state, obs)
        self.assertEqual(second.target, Rect(1310, 1180, 260, 90))
        self.assertTrue(policy.prejourney_progress.profession_filter_done)

    def test_filter_dialog_maps_warrior_alias(self) -> None:
        # docx 正文写「战士」, 游戏 UI 实际叫「突击者」(例: 缇莉雅)。
        self.assertEqual(normalize_profession("战士"), "突击者")
        self.assertEqual(normalize_profession("突击者"), "突击者")
        self.assertEqual(normalize_profession("术士"), "术师")
        self.assertEqual(normalize_profession("术师"), "术师")
        self.assertEqual(normalize_profession(""), "")

    def test_filter_dialog_closes_on_unknown_profession(self) -> None:
        # 不认识的职业配置 normalize 后为空 → 钩子根本不会点漏斗; 若弹窗仍开着
        # (误触/手点), 自愈行为是直接点确认关闭, 不乱选职业。
        policy = TrainerPolicy()
        state = _state(profession="魔法少女")
        payload = FilterDialog(
            profession_buttons={"坦克": Rect(384, 590, 250, 100)},
            confirm_button=Rect(1310, 1180, 260, 90),
        )
        action = policy.decide(state, Observation(Screen.FILTER_DIALOG, 0.95, payload=payload))
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(1310, 1180, 260, 90))

    def test_filter_dialog_pauses_when_button_missing(self) -> None:
        # 配置职业有效, 但弹窗里没解析出对应按钮(区域缺) → pause 等人看, 不乱点。
        policy = TrainerPolicy()
        state = _state(profession="术师")
        payload = FilterDialog(
            profession_buttons={"坦克": Rect(384, 590, 250, 100)},
            confirm_button=Rect(1310, 1180, 260, 90),
        )
        action = policy.decide(state, Observation(Screen.FILTER_DIALOG, 0.95, payload=payload))
        self.assertEqual(action.kind, "pause")

    def test_character_filter_signature(self) -> None:
        self.assertTrue(
            _has_filter_dialog_signature(
                {
                    "filter_dialog_anchor_title": "筛选",
                    "filter_dialog_profession_row": "坦克 突击者 游侠 术师 刺客 辅助",
                }
            )
        )
        # 只有职业词没有筛选标题(角色列表本身也会出现职业词)→ 不认。
        self.assertFalse(
            _has_filter_dialog_signature(
                {"filter_dialog_profession_row": "术师 刺客"}
            )
        )


def _blessing_choice(dropdown_open: bool = False) -> BlessingChoice:
    return BlessingChoice(
        options=[],
        confirm_button=Rect(2210, 1310, 250, 90),
        value_filter_button=Rect(1090, 195, 250, 90),
        attr_filter_button=Rect(1380, 195, 130, 90),
        value_dropdown_ability_item=Rect(1310, 400, 260, 45) if dropdown_open else None,
        grid_origin=Rect(224, 480, 300, 220),
        grid_step_x=320,
        grid_step_y=272,
    )


class ImprintFlowTest(unittest.TestCase):
    """刻印操作流程: 数值筛选→能力值领域→属性筛选→(弹窗选属性)→按序号点卡→确认。"""

    def test_full_imprint_flow_for_slot_2(self) -> None:
        policy = TrainerPolicy()
        # 模拟 BLESSING_SETUP 点开了槽 2(由 decide_blessing_setup 记录)。
        policy.prejourney_progress.extra["current_imprint_slot"] = 2
        state = _state(profession="术师", imprint_slot_2_index=12)

        # 1) 点数值筛选入口。
        a1 = policy.decide(state, Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice()))
        self.assertEqual(a1.target, Rect(1090, 195, 250, 90))

        # 2) 下拉展开 → 点「能力值领域」。
        a2 = policy.decide(
            state, Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice(dropdown_open=True))
        )
        self.assertEqual(a2.target, Rect(1310, 400, 260, 45))

        # 3) 点属性筛选按钮(弹出筛选弹窗)。
        a3 = policy.decide(state, Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice()))
        self.assertEqual(a3.target, Rect(1380, 195, 130, 90))

        # 4) 筛选弹窗(FILTER_DIALOG)被分类出来: 选属性 → 确认。术师→力量。
        dialog = FilterDialog(
            profession_buttons={"术师": Rect(1248, 590, 250, 100)},
            confirm_button=Rect(1310, 1180, 260, 90),
            attribute_buttons={"力量": Rect(384, 750, 250, 95), "体力": Rect(672, 750, 250, 95)},
        )
        a4 = policy.decide(state, Observation(Screen.FILTER_DIALOG, 0.95, payload=dialog))
        self.assertEqual(a4.target, Rect(384, 750, 250, 95))
        a5 = policy.decide(state, Observation(Screen.FILTER_DIALOG, 0.95, payload=dialog))
        self.assertEqual(a5.target, Rect(1310, 1180, 260, 90))

        # 5) 回到刻印网格: 槽 2 配置第 12 个 → 第 3 排第 2 个。
        a6 = policy.decide(state, Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice()))
        self.assertEqual(a6.target, Rect(224 + 320, 480 + 2 * 272, 300, 220))
        self.assertIn("#12", a6.reason)

        # 6) 确认选卡, 流程阶段清空(回 BLESSING_SETUP 后下一个槽重新来)。
        a7 = policy.decide(state, Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice()))
        self.assertEqual(a7.target, Rect(2210, 1310, 250, 90))
        self.assertNotIn("imprint_stage", policy.prejourney_progress.extra)

    def test_no_prejourney_keeps_old_blessing_logic(self) -> None:
        # 不带 prejourney 时, BLESSING_CHOICE 走旧「选最高值祝福」逻辑(回归)。
        policy = TrainerPolicy()
        action = policy.decide(
            GameState(), Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice())
        )
        # 旧逻辑: 没有任何属性匹配选项 → pause(不是点筛选按钮)。
        self.assertEqual(action.kind, "pause")

    def test_blessing_setup_records_slot_and_resets_stage(self) -> None:
        from starsavior_trainer.models import BlessingSetup, BlessingSlot

        policy = TrainerPolicy()
        policy.prejourney_progress.extra["imprint_stage"] = "filtered"
        setup = BlessingSetup(
            slots=[
                BlessingSlot(index=1, occupied=True, target=Rect(1200, 600, 160, 160)),
                BlessingSlot(index=2, occupied=False, target=Rect(2050, 380, 160, 160)),
            ],
            confirm_button=Rect(2280, 1300, 240, 80),
            auto_equip_button=Rect(2000, 1300, 240, 80),
            can_confirm=False,
        )
        action = policy.decide_blessing_setup(setup)
        self.assertEqual(action.target, Rect(2050, 380, 160, 160))
        self.assertEqual(policy.prejourney_progress.extra["current_imprint_slot"], 2)
        self.assertNotIn("imprint_stage", policy.prejourney_progress.extra)


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
