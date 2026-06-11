import unittest
from pathlib import Path

from PIL import Image

from starsavior_trainer.classifier import (
    _classify_journey_origin_by_visual,
    _has_real_event_options,
    _match_screen,
    classify_by_blue_button,
    classify_hybrid,
)
from starsavior_trainer.models import Screen
from starsavior_trainer.ocr import OcrResult
from starsavior_trainer.regions import load_region_profile


class ClassifierTest(unittest.TestCase):
    def test_initial_route_page_accepts_starsavior_title_with_start_button(self) -> None:
        screen, confidence = _match_screen(
            {
                "route_select_anchor_title": "StarSavior",
                "start_button": "\u5f00\u59cb",
            }
        )

        self.assertEqual(screen, Screen.INITIAL)
        self.assertGreaterEqual(confidence, 0.70)

    def test_reward_title_classifies_as_reward(self) -> None:
        screen, confidence = _match_screen({"reward_title": "获得奖励"})

        self.assertEqual(screen, Screen.REWARD)
        self.assertGreaterEqual(confidence, 0.70)

    def test_game_menu_popup_classifies_as_game_menu(self) -> None:
        # The accidental in-game 菜单 popup. Its top-left 菜单 title + centre 观测
        # menu items uniquely identify it, so the bot can click ✕ to close instead
        # of falling to "unknown → click centre" (which would hit 重新观测/观测结束
        # in the centre and restart or end the run).
        screen, confidence = _match_screen(
            {
                "game_menu_anchor_title": "菜单",
                "game_menu_observe_marker": "观测结束 重新观测",
            }
        )

        self.assertEqual(screen, Screen.GAME_MENU)
        self.assertGreaterEqual(confidence, 0.70)

    def test_game_menu_signature_needs_both_title_and_observe_marker(self) -> None:
        # Just the word 菜单 (other screens may show it) must NOT trigger the menu
        # screen — the 观测 menu-item marker is required so we don't false-positive.
        from starsavior_trainer.classifier import _has_game_menu_signature

        self.assertTrue(
            _has_game_menu_signature(
                {"game_menu_anchor_title": "菜单", "game_menu_observe_marker": "重新观测"}
            )
        )
        self.assertFalse(_has_game_menu_signature({"game_menu_anchor_title": "菜单"}))
        self.assertFalse(_has_game_menu_signature({}))

    def test_reward_signature_wins_over_character_select_旅程起点_overlap(self) -> None:
        # The 获得奖励 popup lands over the journey map, whose top-left can still
        # OCR as 旅程起点 (the character_select anchor text). Without the reward
        # signature this scored as character_select and stalled the scroll loop.
        screen, confidence = _match_screen(
            {
                "reward_title": "获得奖励",
                "character_select_anchor_title": "旅程起点",
            }
        )

        self.assertEqual(screen, Screen.REWARD)
        self.assertGreaterEqual(confidence, 0.70)

    def test_visual_journey_origin_detects_character_select(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "character_select_003.png")

        self.assertEqual(_classify_journey_origin_by_visual(image, profile), Screen.CHARACTER_SELECT)

    def test_visual_journey_origin_detects_empty_blessing_setup(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "blessing_setup_empty_001.png")

        self.assertEqual(_classify_journey_origin_by_visual(image, profile), Screen.BLESSING_SETUP)

    def test_visual_journey_origin_detects_ready_blessing_setup(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "blessing_setup_ready_001.png")

        self.assertEqual(_classify_journey_origin_by_visual(image, profile), Screen.BLESSING_SETUP)

    def test_hybrid_visual_override_keeps_blessing_setup_from_becoming_character_select(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "blessing_setup_empty_001.png")

        observation = classify_hybrid(image, profile, _JourneyOriginOcr())

        self.assertEqual(observation.screen, Screen.BLESSING_SETUP)

    def test_hybrid_visual_override_keeps_blessing_choice_from_becoming_character_select(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "blessing_choice_002.png")

        observation = classify_hybrid(image, profile, _JourneyOriginOcr())

        self.assertEqual(observation.screen, Screen.BLESSING_CHOICE)

    def test_route_select_does_not_classify_as_confirm_dialog_by_blue(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "live_blessing_choice_missing_payload.png")

        observation = classify_by_blue_button(image, profile)

        self.assertNotEqual(observation.screen, Screen.CONFIRM_DIALOG)

    def test_confirm_dialog_blue_requires_dialog_panel(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "confirm_dialog_001.png")

        observation = classify_by_blue_button(image, profile)

        self.assertEqual(observation.screen, Screen.CONFIRM_DIALOG)

    def test_battle_anchor_wins_over_training_hub_participation_text(self) -> None:
        screen, confidence = _match_screen(
            {
                "training_hub_anchor_title": "\u53c2\u52a0\u8bc4\u9274\u6218",
                "battle_title": "\u53c2\u52a0\u8bc4\u9274\u6218",
                "battle_entry_button": "\u8bc4\u9274\u6218 \u4e00\u822c",
            }
        )

        self.assertEqual(screen, Screen.BATTLE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_battle_entry_and_accept_classify_as_battle(self) -> None:
        screen, confidence = _match_screen(
            {
                "battle_title": "\u53c2\u52a0\u8bc4\u9274\u6218",
                "battle_entry_button": "\u8bc4\u9274\u6218 \u4e00\u822c",
                "battle_accept_button": "\u63a5\u53d7",
            }
        )

        self.assertEqual(screen, Screen.BATTLE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_commission_battle_confirm_classifies_as_battle(self) -> None:
        # 委托战斗确认界面("XX讨伐委托" + 跳过战斗/开始委托)和评鉴战确认同布局, 也该判 BATTLE
        # → 点跳过战斗。之前 title 只认"评鉴战"→ 委托被误判 event_fast_forward 死循环。
        screen, confidence = _match_screen(
            {
                "battle_skip_battle_button": "跳过战斗",
                "battle_confirm_title": "史莱姆讨伐委托",
            }
        )

        self.assertEqual(screen, Screen.BATTLE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_rating_battle_confirm_classifies_as_battle(self) -> None:
        # 基础评鉴战 entry confirm: a centred dialog whose battle regions (top-corner)
        # read empty, so classify_by_ocr is UNKNOWN and the blue-button fallback
        # misreads the 跳过战斗 blue button as event_fast_forward. The 跳过战斗 button +
        # 评鉴战 title give it a proper BATTLE signature instead.
        screen, confidence = _match_screen(
            {
                "battle_skip_battle_button": "跳过战斗",  # 跳过战斗
                "battle_confirm_title": "基础评鉴战",  # 基础评鉴战
            }
        )

        self.assertEqual(screen, Screen.BATTLE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_training_hub_uses_action_buttons_not_generic_participation(self) -> None:
        screen, confidence = _match_screen(
            {
                "training_hub_anchor_title": "\u8bc4\u9274\u6218",
                "training_hub_distance": "\u8ddd\u79bb\u76ee\u6807 6",
                "training_hub_action_training": "\u8bad\u7ec3",
                "training_hub_action_commission": "\u59d4\u6258",
                "training_hub_action_rest": "\u4f11\u606f",
            }
        )

        self.assertEqual(screen, Screen.TRAINING_HUB)
        self.assertGreaterEqual(confidence, 0.70)

    def test_training_hub_recognizes_trade_and_shop_alert(self) -> None:
        screen, confidence = _match_screen(
            {
                "training_hub_action_shop": "\u4ea4\u6613",
                "training_hub_shop_alert": "\u5168\u65b0\u5546\u54c1\u5230\u8d27\uff01",
                "training_hub_nav_potential": "\u6f5c\u8d28",
            }
        )

        self.assertEqual(screen, Screen.TRAINING_HUB)
        self.assertGreaterEqual(confidence, 0.70)

    def test_training_select_full_card_text_wins_over_hub_overlap(self) -> None:
        screen, confidence = _match_screen(
            {
                "training_hub_action_training": "\u4f53\u529b\u8bad\u7ec3 Lv.1",
                "training_hub_action_rest": "\u4fdd\u62a4\u8bad\u7ec3 Lv.1",
                "training_select_card_power": "\u529b\u91cf\u8bad\u7ec3 Lv.1 \u5931\u8d25\u73870%",
                "training_select_card_stamina": "\u4f53\u529b\u8bad\u7ec3 Lv.1",
            }
        )

        self.assertEqual(screen, Screen.TRAINING_SELECT)
        self.assertGreaterEqual(confidence, 0.70)

    def test_trading_shop_with_training_book_not_misclassified_as_training(self) -> None:
        # The D-DAY trading shop sells a "保护训练的秘笈" item whose name contains
        # 保护训练 — only ONE training-card region reads a training name. A real
        # training screen has all five (力量/体力/韧性/集中/保护训练). Requiring ≥2
        # stops the shop being mis-read as TRAINING_SELECT (which made the training
        # inspector loop forever clicking a non-existent training card).
        from starsavior_trainer.classifier import _has_training_select_signature

        self.assertFalse(
            _has_training_select_signature({"training_select_card_wisdom": "3024 保护训练的秘笈"})
        )
        self.assertTrue(
            _has_training_select_signature(
                {
                    "training_select_card_power": "力量训练 Lv.3",
                    "training_select_card_stamina": "体力训练 Lv.1",
                }
            )
        )

    def test_train_station_classifies_as_region_move(self) -> None:
        # The 列车月台 region-move screen (地区移动 + 列车月台) was mis-scored as
        # relic_choice by the fallback and got stuck. Its two anchors uniquely
        # identify REGION_MOVE so the bot can pick a destination and travel.
        screen, confidence = _match_screen(
            {
                "region_move_anchor_title": "地区移动",
                "region_move_station_title": "列车月台",
            }
        )

        self.assertEqual(screen, Screen.REGION_MOVE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_rest_submenu_signature_wins_over_battle_overlap(self) -> None:
        screen, confidence = _match_screen(
            {
                "battle_title": "\u53c2\u52a0\u8bc4\u9274\u6218",
                "battle_accept_button": "\u4f11\u606f",
                "rest_submenu_option_1": "\u9732\u5bbf \u514d\u8d39",
                "rest_submenu_option_2": "\u4f4f\u5904 30",
                "rest_submenu_option_3": "\u51a5\u60f3\u5ba4 60",
            }
        )

        self.assertEqual(screen, Screen.REST_SUBMENU)
        self.assertGreaterEqual(confidence, 0.70)

    def test_shop_signature_wins_over_battle_overlap(self) -> None:
        # Journey Trading (交易) sits on the D-DAY background, so battle_title OCRs
        # 参加评鉴战 (a BATTLE anchor word) — without a shop signature it falls to
        # fallback scoring and misclassifies as BATTLE (1.00). The 购买 button plus
        # the selected item's effect detail identify the trading screen instead.
        screen, confidence = _match_screen(
            {
                "battle_title": "参加评鉴战",  # 参加评鉴战
                "shop_buy_button": "购买",  # 购买
                "shop_detail_effect": "潜质点数8退还",  # 潜质点数8退还
                "shop_item_2_name": "高级牛肉义",  # 高级牛肉义
            }
        )

        self.assertEqual(screen, Screen.SHOP)
        self.assertGreaterEqual(confidence, 0.70)

    def test_shop_signature_via_refresh_when_no_item_selected(self) -> None:
        # 刚进交易界面 / 没选中任何商品时, 中间详情和底部「购买」按钮都不显示, 只有右上
        # 「刷新」常驻 + 右侧商品列表。签名必须靠「刷新」识别(否则像实机那样 unknown)。
        screen, confidence = _match_screen(
            {
                "battle_title": "参加评鉴战",  # D-DAY 背景(否则会兜底成 BATTLE)
                "shop_refresh_button": "刷新",  # 刷新
                "shop_item_3_name": "身风扇",  # 身风扇
                "shop_item_3_price": "40",
            }
        )

        self.assertEqual(screen, Screen.SHOP)
        self.assertGreaterEqual(confidence, 0.70)

    def test_journey_dialogue_text_wins_over_event_choice_title(self) -> None:
        screen, confidence = _match_screen(
            {
                "event_choice_title": "\u65c5\u7a0b\u4e8b\u4ef6",
                "dialogue_journey_event_label": "\u65c5\u7a0b\u4e8b\u4ef6",
                "dialogue_journey_text_area": "\u514b\u83b1\u513f\u83b7\u5f97\u4e86\u661f\u4e4b\u795d\u798f!",
            }
        )

        self.assertEqual(screen, Screen.DIALOGUE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_event_choice_options_win_over_dialogue_event_label_overlap(self) -> None:
        screen, confidence = _match_screen(
            {
                "event_choice_title": "\u65c5\u7a0b\u4e8b\u4ef6 \u5de5\u574a\u7684\u5ba3\u4f20\u7b56\u7565",
                "event_choice_option_1": "\u4ed8\u94b1\u8d2d\u4e70\u3002 50",
                "event_choice_option_2": "\u5bfb\u627e\u5f31\u70b9\u653b\u63a0\u3002 70",
                "dialogue_journey_event_label": "\u65c5\u7a0b\u4e8b\u4ef6 \u5de5\u574a\u7684\u5ba3\u4f20\u7b56\u7565",
            }
        )

        self.assertEqual(screen, Screen.EVENT_CHOICE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_journey_dialogue_uses_bottom_text_even_without_reward_word(self) -> None:
        screen, confidence = _match_screen(
            {
                "event_choice_title": "\u65c5\u7a0b\u4e8b\u4ef6",
                "dialogue_journey_event_label": "\u963f\u5c14\u514b\u90a3\u4e8b\u4ef6",
                "dialogue_journey_text_area": "\u542c\u8bf4\u4e86\u51cc\u7a7f\u4e0a\u73b0\u5728\u8fd9\u8eab\u8863\u670d\u7684\u5951\u673a\u3002",
            }
        )

        self.assertEqual(screen, Screen.DIALOGUE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_post_training_success_wins_over_other_overlap(self) -> None:
        screen, confidence = _match_screen(
            {
                "relic_choice_confirm_button": "IMR",
                "post_training_title": "\u529b\u91cf\u8bad\u7ec3 Lv.1",
                "post_training_success_text": "\u8bad\u7ec3\u6210\u529f!",
            }
        )

        self.assertEqual(screen, Screen.POST_TRAINING)
        self.assertGreaterEqual(confidence, 0.70)

    def test_commission_select_signature_wins_over_training_hub_when_options_have_text(self) -> None:
        screen, confidence = _match_screen(
            {
                "commission_select_anchor_title": "\u53c2\u52a0\u8bc4\u9274\u6218",
                "commission_select_option_1_name": "\u53f2\u83b1\u59c6\u8ba8\u4f10\u59d4\u6258",
                "commission_select_option_2_name": "\u53f2\u83b1\u59c6\u8ba8\u4f10\u59d4\u6258",
                "commission_select_accept_button": "\u63a5\u53d7",
                "training_hub_anchor_title": "\u59d4\u6258",
                "training_hub_action_commission": "\u59d4\u6258",
            }
        )

        self.assertEqual(screen, Screen.COMMISSION_SELECT)
        self.assertGreaterEqual(confidence, 0.70)

    def test_commission_select_requires_anchor_keyword_to_distinguish_from_blessing_setup(self) -> None:
        screen, confidence = _match_screen(
            {
                "commission_select_anchor_title": "\u65c5\u7a0b\u8d77\u70b9",
                "commission_select_option_1_name": "\u65c5\u7a0b\u8d77\u70b9",
                "commission_select_option_2_name": "\u65c5\u7a0b\u8d77\u70b9",
            }
        )

        self.assertNotEqual(screen, Screen.COMMISSION_SELECT)


    def test_intro_skip_button_classifies_as_dialogue(self) -> None:
        # The story-intro cutscene's only reliable text anchor is its top-right
        # "SKIP" button; the dialogue signature must catch it (case-insensitively)
        # so the intro isn't left UNKNOWN (which fell through to a ~3.6s sweep).
        screen, confidence = _match_screen({"dialogue_intro_skip_button": "SKIP"})

        self.assertEqual(screen, Screen.DIALOGUE)
        self.assertGreaterEqual(confidence, 0.70)

    def test_has_real_event_options_false_when_option_rows_blank(self) -> None:
        # A journey DIALOGUE shares the "\u65c5\u7a0b\u4e8b\u4ef6" title but has no option rows.
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.new("RGB", (2560, 1440))

        self.assertFalse(_has_real_event_options(image, profile, _FixedOcr("")))

    def test_has_real_event_options_true_when_option_row_has_text(self) -> None:
        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.new("RGB", (2560, 1440))

        self.assertTrue(_has_real_event_options(image, profile, _FixedOcr("\u5bf9\u653b\u51fb\u6709\u5e2e\u52a9\u7684\u8bad\u7ec3\u6559\u6750")))


class _JourneyOriginOcr:
    def read_text(self, _image: Image.Image) -> OcrResult:
        return OcrResult(text="\u65c5\u7a0b\u8d77\u70b9", confidence=0.99)


class _FixedOcr:
    """OCR stub that returns the same text for every region (for option-row tests)."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self, _image: Image.Image) -> OcrResult:
        return OcrResult(text=self._text, confidence=0.99)


if __name__ == "__main__":
    unittest.main()
