import unittest
from pathlib import Path

from PIL import Image

from starsavior_trainer.classifier import (
    _classify_journey_origin_by_visual,
    _match_screen,
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

    def test_battle_accept_detail_tolerates_common_ocr_typo(self) -> None:
        screen, confidence = _match_screen(
            {
                "battle_title": "\u53c2\u52a0\u8bc4\u9274\u6218",
                "battle_entry_button": "\u5e73\u9274\u6218 \u4e00\u822c",
                "battle_accept_button": "\u63a5\u53d7",
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


class _JourneyOriginOcr:
    def read_text(self, _image: Image.Image) -> OcrResult:
        return OcrResult(text="\u65c5\u7a0b\u8d77\u70b9", confidence=0.99)


if __name__ == "__main__":
    unittest.main()
