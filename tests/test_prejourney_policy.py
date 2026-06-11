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


def _blessing_choice(star: bool = True, star_active: bool = False) -> BlessingChoice:
    return BlessingChoice(
        options=[],
        confirm_button=Rect(2210, 1310, 250, 90),
        star_filter_button=Rect(1704, 173, 53, 47) if star else None,
        star_filter_active=star_active,
    )


class ImprintStarFlowTest(unittest.TestCase):
    """刻印操作(2026-06-12 拍板): 星标暗→点亮过滤出祝福; 亮→旧逻辑选最高值。

    星标是 toggle 且游戏跨界面记住状态(实跑教训: 槽2 进来已亮, 盲点会关掉
    过滤)→ 必须按画面像素状态决定, 不按"点没点过"记忆。
    """

    def test_star_dark_clicks_to_enable(self) -> None:
        policy = TrainerPolicy()
        action = policy.decide(
            GameState(),
            Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice(star_active=False)),
        )
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(1704, 173, 53, 47))
        self.assertIn("star", action.reason)

    def test_star_already_lit_skips_click(self) -> None:
        # 槽2 场景: 星标已亮(槽1 开过, 游戏记住了)→ 绝不再点, 直接旧逻辑。
        policy = TrainerPolicy()
        action = policy.decide(
            GameState(),
            Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice(star_active=True)),
        )
        # 旧逻辑: 没有属性匹配选项(options 空)→ pause, 而不是点星标。
        self.assertEqual(action.kind, "pause")

    def test_star_state_detection_thresholds(self) -> None:
        # 像素检测: 开=白底亮按钮(实测81%亮), 关=深色(0%)。阈值40%。
        from PIL import Image as PILImage

        from starsavior_trainer.screen_reader import _star_filter_is_active

        rect = Rect(1704, 173, 53, 47)
        lit = PILImage.new("RGB", (2560, 1440), (64, 64, 64))
        lit.paste(PILImage.new("RGB", (53, 47), (225, 220, 210)), (1704, 173))
        self.assertTrue(_star_filter_is_active(lit, rect))
        dark = PILImage.new("RGB", (2560, 1440), (64, 64, 64))
        self.assertFalse(_star_filter_is_active(dark, rect))
        self.assertFalse(_star_filter_is_active(None, rect))

    def test_star_region_missing_falls_back_to_old_logic(self) -> None:
        # 星标区域未配置(其他分辨率 profile)→ 直接旧逻辑, 不点不崩。
        policy = TrainerPolicy()
        action = policy.decide(
            GameState(), Observation(Screen.BLESSING_CHOICE, 0.95, payload=_blessing_choice(star=False))
        )
        self.assertEqual(action.kind, "pause")

    def test_blessing_setup_records_slot(self) -> None:
        from starsavior_trainer.models import BlessingSetup, BlessingSlot

        policy = TrainerPolicy()
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


class SupportDeckAndFriendTest(unittest.TestCase):
    """支援卡: 卡组切换(圆点检测)+ 好友卡借用流程。"""

    @staticmethod
    def _journey(current_deck: int | None) -> "JourneyStart":
        from starsavior_trainer.models import JourneyStart

        return JourneyStart(
            start_button=Rect(1932, 1306, 535, 75),
            arcana_slots=[Rect(1400 + i * 200, 443, 180, 328) for i in range(5)],
            current_deck=current_deck,
            previous_button=Rect(1340, 620, 62, 92),
            next_button=Rect(2420, 620, 62, 92),
        )

    def test_journey_start_always_clicked_regardless_of_config(self) -> None:
        # 2026-06-12 拍板: 支援卡(卡组/好友卡)用户人工配置, bot 不碰 ——
        # 无论配置什么, 这个画面永远直接点「旅程起点」。
        policy = TrainerPolicy()
        state = _state(support_deck=4, friend_support_name="B站老顾不烦")
        for deck in (None, 2, 4):
            action = policy.decide(
                state, Observation(Screen.JOURNEY_START, 0.95, payload=self._journey(current_deck=deck))
            )
            self.assertEqual(action.target, Rect(1932, 1306, 535, 75))  # 旅程起点

    def test_support_picker_with_borrow_opens_friend_list(self) -> None:
        from starsavior_trainer.models import SupportPicker

        policy = TrainerPolicy()
        state = _state(friend_support_name="B站老顾不烦")
        payload = SupportPicker(
            back_button=Rect(60, 105, 90, 85),
            friend_button=Rect(100, 430, 290, 80),
            has_borrow=True,
        )
        action = policy.decide(state, Observation(Screen.SUPPORT_PICKER, 0.95, payload=payload))
        self.assertEqual(action.target, Rect(100, 430, 290, 80))

    def test_support_picker_without_borrow_backs_out_and_skips(self) -> None:
        from starsavior_trainer.models import SupportPicker

        policy = TrainerPolicy()
        state = _state(friend_support_name="B站老顾不烦")
        payload = SupportPicker(back_button=Rect(60, 105, 90, 85), friend_button=None, has_borrow=False)
        action = policy.decide(state, Observation(Screen.SUPPORT_PICKER, 0.95, payload=payload))
        self.assertEqual(action.target, Rect(60, 105, 90, 85))
        self.assertTrue(policy.prejourney_progress.friend_card_done)

    def test_friend_list_picks_matching_card(self) -> None:
        from starsavior_trainer.models import SupportFriendCard, SupportFriendList

        policy = TrainerPolicy()
        state = _state(friend_support_name="B站老顾不烦")
        payload = SupportFriendList(
            cards=[
                SupportFriendCard(name="Daybreaker", target=Rect(858, 850, 250, 250)),
                SupportFriendCard(name="B站老顾不烦", target=Rect(490, 850, 250, 250)),
            ]
        )
        action = policy.decide(state, Observation(Screen.SUPPORT_FRIEND_LIST, 0.95, payload=payload))
        self.assertEqual(action.target, Rect(490, 850, 250, 250))

    def test_friend_list_pauses_when_not_found(self) -> None:
        from starsavior_trainer.models import SupportFriendCard, SupportFriendList

        policy = TrainerPolicy()
        state = _state(friend_support_name="B站老顾不烦")
        payload = SupportFriendList(
            cards=[SupportFriendCard(name="Daybreaker", target=Rect(858, 850, 250, 250))]
        )
        action = policy.decide(state, Observation(Screen.SUPPORT_FRIEND_LIST, 0.95, payload=payload))
        self.assertEqual(action.kind, "pause")

    def test_card_detail_confirms_and_marks_done(self) -> None:
        from starsavior_trainer.models import SupportCardDetail

        policy = TrainerPolicy()
        state = _state(friend_support_name="B站老顾不烦")
        payload = SupportCardDetail(select_button=Rect(2210, 990, 250, 95))
        action = policy.decide(state, Observation(Screen.SUPPORT_CARD_DETAIL, 0.95, payload=payload))
        self.assertEqual(action.target, Rect(2210, 990, 250, 95))
        self.assertTrue(policy.prejourney_progress.friend_card_done)


class DeckDotDetectionTest(unittest.TestCase):
    """卡组指示圆点检测: 5 段取最亮; 区分度不足返回 None。"""

    def test_detects_third_dot(self) -> None:
        from PIL import Image as PILImage

        from starsavior_trainer.screen_reader import _detect_active_deck_dot

        strip = PILImage.new("RGB", (250, 40), (40, 40, 60))
        for x in range(100, 150):  # 第 3 段(50px/段)涂亮白
            for y in range(40):
                strip.putpixel((x, y), (240, 240, 250))
        image = PILImage.new("RGB", (2560, 1440), (10, 10, 20))
        image.paste(strip, (1800, 940))
        self.assertEqual(_detect_active_deck_dot(image, Rect(1800, 940, 250, 40)), 3)

    def test_uniform_strip_returns_none(self) -> None:
        from PIL import Image as PILImage

        from starsavior_trainer.screen_reader import _detect_active_deck_dot

        image = PILImage.new("RGB", (2560, 1440), (60, 60, 70))
        self.assertIsNone(_detect_active_deck_dot(image, Rect(1800, 940, 250, 40)))


if __name__ == "__main__":
    unittest.main()
