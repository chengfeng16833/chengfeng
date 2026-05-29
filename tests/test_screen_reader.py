import unittest
from pathlib import Path

from PIL import Image

from starsavior_trainer.models import (
    BattleScene,
    BlessingChoice,
    BlessingSetup,
    CharacterSelect,
    ConfirmDialog,
    CommissionChoice,
    CommissionOption,
    EventFastForwardSetting,
    EventOption,
    JourneyStart,
    Rect,
    RestSubmenu,
    ShopItem,
    SkillOption,
    TrainingChoice,
    TrainingHubStatus,
)
from starsavior_trainer.ocr import OcrResult
from starsavior_trainer.regions import RegionProfile
from starsavior_trainer.screen_reader import (
    PostTrainingResult,
    RegionOcrReader,
    RegionText,
    contains_any_text,
    extract_character_name,
    normalize_ocr_text,
    parse_attribute_value,
    parse_battle,
    parse_blessing_choice,
    parse_blessing_setup,
    parse_character_select,
    parse_commission_select,
    parse_confirm_dialog,
    parse_dialogue_scene,
    parse_event_choice,
    parse_event_fast_forward_setting,
    parse_first_int,
    parse_journey_start,
    parse_percent,
    parse_post_training,
    parse_region_move,
    parse_relic_choice,
    parse_relic_name,
    parse_rest_submenu,
    parse_shop,
    parse_skill_select,
    parse_training_direction,
    _match_character_variants,
    parse_training_hub,
    parse_training_select,
    looks_like_ocr_region,
)


class ScreenReaderParserTest(unittest.TestCase):
    # ---- character variant association (同名2形态) ----
    def test_match_character_variants_associates_text_below_name(self) -> None:
        # 形态文字(COSMIC/ANOTHER)在对应名字行正下方 ~38px(实机: 莱希名字 y359, COSMIC y397)。
        # 普通角色名字下方无形态文字 → ""。
        names = [("莱希", 359), ("萝贝塔", 505), ("卡蜜", 636), ("卡蜜", 780)]
        variants = [("COSMIC", 397), ("ANOTHER", 818)]
        result = _match_character_variants(names, variants)
        self.assertEqual(result, ["COSMIC", "", "", "ANOTHER"])

    def test_match_character_variants_tolerates_ocr_noise(self) -> None:
        # OCR 可能把 ANOTHER/COSMIC 读残/读脏, 要容错规范化。
        names = [("卡蜜", 636)]
        variants = [("AN0THE", 674)]  # 缺尾字母 + 0/O 混
        result = _match_character_variants(names, variants)
        self.assertEqual(result, ["ANOTHER"])

    def test_match_character_variants_ignores_far_text(self) -> None:
        # 距离过远(不在名字正下方)的文字不关联(避免串行)。
        names = [("卡蜜", 636)]
        variants = [("COSMIC", 900)]  # 离 636 太远
        result = _match_character_variants(names, variants)
        self.assertEqual(result, [""])

    # ---- existing helpers ----
    def test_normalize_ocr_text_handles_common_width_and_case_noise(self) -> None:
        self.assertEqual(normalize_ocr_text("  Fail\uff05  "), "fail%")
        self.assertEqual(normalize_ocr_text("\u3000MOVE\u3000"), "move")

    def test_contains_any_text_uses_normalized_text(self) -> None:
        self.assertTrue(contains_any_text("\u3000MOVE\uff05", ["move"]))
        self.assertFalse(contains_any_text("sleep", ["meditation"]))

    def test_looks_like_ocr_region_distinguishes_text_regions_from_click_regions(self) -> None:
        self.assertTrue(looks_like_ocr_region("relic_choice_card_2_name"))
        self.assertTrue(looks_like_ocr_region("confirm_dialog_message"))
        self.assertFalse(looks_like_ocr_region("game_client"))
        self.assertFalse(looks_like_ocr_region("relic_choice_card_2"))

    def test_parse_first_int_reads_digits_and_commas(self) -> None:
        self.assertEqual(parse_first_int("coins 1,260"), 1260)
        self.assertEqual(parse_first_int("fail O5%"), 5)
        self.assertEqual(parse_first_int("\u529b\u91cf:3S"), 35)
        self.assertIsNone(parse_first_int("no number"))

    def test_parse_percent_prefers_percent_value(self) -> None:
        self.assertEqual(parse_percent("failure 12%"), 12)
        self.assertEqual(parse_percent("failure 12\uff05"), 12)
        self.assertEqual(parse_percent("fail O5%"), 5)
        self.assertEqual(parse_percent("fail S%"), 5)

    def test_parse_percent_falls_back_to_first_number(self) -> None:
        self.assertEqual(parse_percent("failure 28"), 28)
        self.assertIsNone(parse_percent("unknown"))

    def test_parse_attribute_value_reads_blessing_text(self) -> None:
        self.assertEqual(parse_attribute_value("\u529b\u91cf:35"), ("power", 35))
        self.assertEqual(parse_attribute_value("\u529b\u91cf:3S"), ("power", 35))
        self.assertEqual(parse_attribute_value("\u4f53\u529b\uff1a35"), ("stamina", 35))
        self.assertEqual(parse_attribute_value("\u8010\u529b 50"), ("stamina", 50))
        self.assertEqual(parse_attribute_value("power 45"), ("power", 45))

    def test_parse_attribute_value_returns_none_without_attribute_or_value(self) -> None:
        self.assertIsNone(parse_attribute_value("\u529b\u91cf"))
        self.assertIsNone(parse_attribute_value("score 8,657"))

    # ---- dialogue ----
    def test_parse_character_select_builds_selected_payload(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"character_select_anchor_title": Rect(330, 66, 230, 58), "character_selected_name": Rect(258, 398, 260, 56), "character_select_button": Rect(2038, 1305, 448, 75)})
        selection = parse_character_select([RegionText("character_select_anchor_title", "\u65c5\u7a0b\u8d77\u70b9", 0.9), RegionText("character_selected_name", "\u514b\u83b1\u513f", 0.9)], profile)
        self.assertIsNotNone(selection)
        self.assertIsInstance(selection, CharacterSelect)
        self.assertEqual(selection.selected_name, "\u514b\u83b1\u513f")
        self.assertEqual(selection.confirm_button, profile.regions["character_select_button"])

    def test_extract_character_name_strips_rank_and_icon_noise(self) -> None:
        # Typical OCR output from character_option_N regions
        self.assertEqual(extract_character_name("2O XXX \u840d\u8d1d\u5854"), "\u840d\u8d1d\u5854")
        self.assertEqual(extract_character_name("2O \u8fbe\u5a1c"), "\u8fbe\u5a1c")
        self.assertEqual(extract_character_name("\u53cc9 \u5eb7 \u514b\u83b1\u513f"), "\u514b\u83b1\u513f")
        self.assertEqual(extract_character_name("\u53cc9 XXX \u7f07\u8389\u96c5"), "\u7f07\u8389\u96c5")
        self.assertEqual(extract_character_name("D 29 xxX \u7f57\u838e\u8389\u4e9a"), "\u7f57\u838e\u8389\u4e9a")
        self.assertEqual(extract_character_name("25 XxX \u83b1\u5e0c"), "\u83b1\u5e0c")
        self.assertEqual(extract_character_name("24 XXX \u8299\u84fe"), "\u8299\u84fe")

    def test_extract_character_name_returns_none_for_empty_input(self) -> None:
        self.assertIsNone(extract_character_name(""))
        self.assertIsNone(extract_character_name("XXX 123 ABC"))

    def test_parse_character_select_includes_list_options(self) -> None:
        # Profile with character_option_1..3 in addition to the base regions
        confirm = Rect(2038, 1305, 448, 75)
        opt1_rect = Rect(2030, 250, 458, 122)
        opt2_rect = Rect(2030, 394, 458, 122)
        opt3_rect = Rect(2030, 540, 458, 122)
        profile = RegionProfile(
            "test",
            (2560, 1440),
            {
                "character_select_anchor_title": Rect(330, 66, 230, 58),
                "character_selected_name": Rect(258, 398, 260, 56),
                "character_select_button": confirm,
                "character_option_1": opt1_rect,
                "character_option_2": opt2_rect,
                "character_option_3": opt3_rect,
            },
        )
        region_texts = [
            RegionText("character_select_anchor_title", "\u65c5\u7a0b\u8d77\u70b9", 0.9),
            RegionText("character_selected_name", "\u514b\u83b1\u513f", 0.9),
            # Noisy OCR output for the list slots
            RegionText("character_option_1", "\u53cc0 XXX \u840d\u8d1d\u5854", 0.68),
            RegionText("character_option_2", "\u53cc0 \u8fbe\u5a1c", 0.69),
            RegionText("character_option_3", "\u53cc9 \u5eb7 \u514b\u83b1\u513f", 0.57),
        ]
        selection = parse_character_select(region_texts, profile)

        self.assertIsNotNone(selection)
        names = [opt.name for opt in selection.options]
        self.assertIn("\u840d\u8d1d\u5854", names)   # \u841d\u8d1d\u5854
        self.assertIn("\u8fbe\u5a1c", names)           # \u8fbe\u5a1c
        self.assertIn("\u514b\u83b1\u513f", names)     # \u514b\u83b1\u513f

        # The selected character should be marked correctly
        kelaier = next(opt for opt in selection.options if opt.name == "\u514b\u83b1\u513f")
        self.assertTrue(kelaier.selected)
        # Click target for list entries should be the option rect, not the confirm button
        naibeta = next(opt for opt in selection.options if opt.name == "\u840d\u8d1d\u5854")
        self.assertEqual(naibeta.target, opt1_rect)

    def test_parse_blessing_setup_reads_empty_slots(self) -> None:
        profile = _blessing_setup_profile()
        setup = parse_blessing_setup([RegionText("blessing_setup_anchor_title", "\u65c5\u7a0b\u8d77\u70b9", 0.9)], profile)
        self.assertIsNotNone(setup)
        self.assertIsInstance(setup, BlessingSetup)
        self.assertFalse(setup.can_confirm)
        self.assertFalse(any(slot.occupied for slot in setup.slots))

    def test_parse_blessing_setup_does_not_treat_blue_confirm_as_filled_slots(self) -> None:
        profile = _blessing_setup_profile()
        image = Image.new("RGB", profile.resolution, (30, 30, 30))
        button = profile.regions["blessing_confirm_button"]
        image.paste((45, 140, 225), (button.x, button.y, button.x + button.width, button.y + button.height))
        setup = parse_blessing_setup([RegionText("blessing_setup_anchor_title", "\u65c5\u7a0b\u8d77\u70b9", 0.9)], profile, image)
        self.assertIsNotNone(setup)
        self.assertTrue(setup.can_confirm)
        self.assertFalse(any(slot.occupied for slot in setup.slots))

    def test_parse_blessing_setup_reads_filled_slots_from_slot_images(self) -> None:
        profile = _blessing_setup_profile()
        image = Image.new("RGB", profile.resolution, (30, 30, 30))
        button = profile.regions["blessing_confirm_button"]
        image.paste((45, 140, 225), (button.x, button.y, button.x + button.width, button.y + button.height))
        for slot_name in ("blessing_slot_1", "blessing_slot_2"):
            slot = profile.regions[slot_name]
            image.paste((105, 105, 105), (slot.x, slot.y, slot.x + slot.width, slot.y + slot.height))
            image.paste((230, 230, 230), (slot.x, slot.y, slot.x + slot.width // 2, slot.y + slot.height))
        setup = parse_blessing_setup([RegionText("blessing_setup_anchor_title", "\u65c5\u7a0b\u8d77\u70b9", 0.9)], profile, image)
        self.assertIsNotNone(setup)
        self.assertTrue(setup.can_confirm)
        self.assertTrue(all(slot.occupied for slot in setup.slots))

    def test_parse_blessing_choice_reads_attribute_cards(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"blessing_choice_anchor_archive": Rect(160, 215, 200, 60), "blessing_card_01": Rect(552, 270, 190, 210), "blessing_card_02": Rect(802, 270, 190, 210), "blessing_choice_confirm_button": Rect(1842, 1294, 525, 75)})
        choice = parse_blessing_choice([RegionText("blessing_choice_anchor_archive", "\u661f\u8fb0\u6863\u6848", 0.9), RegionText("blessing_card_01_attribute", "\u529b\u91cf:35", 0.9), RegionText("blessing_card_02_attribute", "\u4f53\u529b:50", 0.9)], profile)
        self.assertIsNotNone(choice)
        self.assertIsInstance(choice, BlessingChoice)
        self.assertEqual([(item.attribute, item.value) for item in choice.options], [("power", 35), ("stamina", 50)])

    def test_parse_blessing_choice_reads_detail_sub_blessing_count(self) -> None:
        from starsavior_trainer.regions import load_region_profile

        profile = load_region_profile("config/regions/2560x1440.json")
        image = Image.open(Path("screenshots") / "blessing_choice_002.png")

        choice = parse_blessing_choice(
            [
                RegionText("blessing_choice_anchor_archive", "\u661f\u8fb0\u6863\u6848", 0.9),
                RegionText("blessing_card_01_attribute", "\u529b\u91cf:35", 0.9),
                RegionText("blessing_card_02_attribute", "\u529b\u91cf:35", 0.9),
            ],
            profile,
            image,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.detail_sub_blessing_count, 2)
        self.assertEqual([option.sub_blessing_count for option in choice.options], [0, 0])

    def test_parse_journey_start_uses_profile_buttons(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"journey_start_anchor_title": Rect(330, 66, 230, 58), "journey_start_button": Rect(1932, 1306, 535, 75), "journey_start_auto_journey_button": Rect(1620, 1306, 298, 75), "journey_start_arcana_slot_1": Rect(1400, 443, 180, 328)})
        journey = parse_journey_start([RegionText("journey_start_anchor_title", "\u65c5\u7a0b\u8d77\u70b9", 0.9)], profile)
        self.assertIsNotNone(journey)
        self.assertIsInstance(journey, JourneyStart)
        self.assertEqual(journey.start_button, profile.regions["journey_start_button"])

    def test_parse_journey_start_ignores_noisy_title_when_start_button_exists(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"journey_start_anchor_title": Rect(330, 66, 230, 58), "journey_start_button": Rect(1932, 1306, 535, 75)})
        journey = parse_journey_start([RegionText("journey_start_anchor_title", "StarSavior", 1.0)], profile)
        self.assertIsNotNone(journey)
        self.assertEqual(journey.start_button, profile.regions["journey_start_button"])

    def test_parse_confirm_dialog_reads_buttons(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"confirm_dialog_title": Rect(675, 420, 260, 62), "confirm_dialog_message": Rect(1150, 790, 260, 48), "confirm_dialog_confirm_button": Rect(1290, 941, 357, 75), "confirm_dialog_cancel_button": Rect(913, 941, 357, 75)})
        dialog = parse_confirm_dialog([RegionText("confirm_dialog_title", "\u5165\u573a\u786e\u8ba4", 0.9), RegionText("confirm_dialog_message", "\u662f\u5426\u8981\u8fdb\u884c\u65c5\u7a0b", 0.9)], profile)
        self.assertIsNotNone(dialog)
        self.assertIsInstance(dialog, ConfirmDialog)
        self.assertEqual(dialog.confirm_button, profile.regions["confirm_dialog_confirm_button"])

    def test_parse_confirm_dialog_falls_back_to_button_when_ocr_is_blank(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"confirm_dialog_title": Rect(675, 420, 260, 62), "confirm_dialog_confirm_button": Rect(1290, 941, 357, 75)})
        dialog = parse_confirm_dialog([RegionText("confirm_dialog_title", "", 0.0)], profile)
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.confirm_button, profile.regions["confirm_dialog_confirm_button"])

    def test_parse_event_fast_forward_detects_selected_all_checkbox(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"event_fast_forward_title": Rect(525, 366, 310, 62), "event_fast_forward_no_option": Rect(552, 487, 472, 374), "event_fast_forward_watched_option": Rect(1044, 487, 472, 374), "event_fast_forward_all_option": Rect(1526, 476, 492, 394), "event_fast_forward_all_checkbox": Rect(1934, 505, 60, 60), "event_fast_forward_confirm_button": Rect(1102, 1005, 358, 75)})
        image = Image.new("RGB", profile.resolution, (30, 30, 30))
        box = profile.regions["event_fast_forward_all_checkbox"]
        image.paste((45, 140, 225), (box.x, box.y, box.x + box.width, box.y + box.height))
        setting = parse_event_fast_forward_setting([RegionText("event_fast_forward_title", "\u4e8b\u4ef6\u5feb\u8f6c\u8bbe\u5b9a", 0.9)], profile, image)
        self.assertIsNotNone(setting)
        self.assertIsInstance(setting, EventFastForwardSetting)
        self.assertEqual(setting.selected_mode, "all_events")

    def test_parse_dialogue_scene_uses_intro_skip_text(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"dialogue_intro_skip_button": Rect(2350, 55, 145, 60), "dialogue_intro_text_area": Rect(0, 1125, 2560, 315)})
        scene = parse_dialogue_scene([RegionText("dialogue_intro_skip_button", "SKIP", 0.98)], profile)
        self.assertIsNotNone(scene)
        self.assertEqual(scene.skip_button, profile.regions["dialogue_intro_skip_button"])
        self.assertEqual(scene.variant, "intro_story")

    def test_parse_dialogue_scene_uses_journey_hud_anchor_when_skip_has_no_text(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"dialogue_journey_skip_button": Rect(1855, 54, 78, 65), "dialogue_journey_text_area": Rect(640, 1160, 1280, 170)})
        scene = parse_dialogue_scene([RegionText("dialogue_journey_text_area", "\u7f57\u838e\u8389\u4e9a\u83b7\u5f97\u4e86 \u661f\u4e4b\u795d\u798f!", 0.92)], profile)
        self.assertIsNotNone(scene)
        self.assertEqual(scene.skip_button, profile.regions["dialogue_journey_skip_button"])
        self.assertEqual(scene.variant, "journey_hud")

    def test_parse_dialogue_scene_uses_event_label_and_bottom_text(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"dialogue_journey_skip_button": Rect(1855, 54, 78, 65), "dialogue_journey_text_area": Rect(640, 1160, 1280, 170)})
        scene = parse_dialogue_scene(
            [
                RegionText("dialogue_journey_event_label", "\u963f\u5c14\u514b\u90a3\u4e8b\u4ef6", 0.9),
                RegionText("dialogue_journey_text_area", "\u542c\u8bf4\u4e86\u51cc\u7a7f\u4e0a\u73b0\u5728\u8fd9\u8eab\u8863\u670d\u7684\u5951\u673a\u3002", 0.92),
            ],
            profile,
        )
        self.assertIsNotNone(scene)
        self.assertEqual(scene.skip_button, profile.regions["dialogue_journey_skip_button"])

    def test_parse_dialogue_scene_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"dialogue_journey_skip_button": Rect(1855, 54, 78, 65)})
        self.assertIsNone(parse_dialogue_scene([RegionText("other", "training", 0.9)], profile))

    # ---- relic ----
    def test_parse_relic_name_reads_known_initial_relics(self) -> None:
        self.assertEqual(parse_relic_name("\u8f6f\u7ef5\u7ef5\u7684\u73a9\u5076\u670b\u53cb"), "soft_toy_friend")
        self.assertEqual(parse_relic_name("\u70e6\u4eba\u7684\u5e03\u8c37\u9e1f\u65f6\u949f"), "annoying_cuckoo_clock")
        self.assertEqual(parse_relic_name("\u5e73\u8861\u7684\u5929\u79e4"), "balanced_scale")

    def test_parse_relic_name_keeps_unknown_relic_names(self) -> None:
        # Non-first-round relics aren't in the alias table \u2014 keep their raw name so
        # the card isn't dropped and isn't labelled "unknown_relic_N". A highlighted
        # card whose name OCRs slightly garbled must still be kept.
        self.assertEqual(parse_relic_name("\u53e4\u4ee3\u6551\u63f4\u8005\u7684\u5e3d\u5b50"), "\u53e4\u4ee3\u6551\u63f4\u8005\u7684\u5e3d\u5b50")
        self.assertEqual(parse_relic_name("\u4ee3\u6551\u62e8\u8005\u7684\u624b"), "\u4ee3\u6551\u62e8\u8005\u7684\u624b")
        self.assertIsNone(parse_relic_name(""))
        self.assertIsNone(parse_relic_name("   "))

    def test_parse_relic_choice_keeps_selected_card_with_garbled_name(self) -> None:
        # Regression: the highlighted card (garbled name, blank score) used to be
        # dropped because both name and score were None. It must now be kept.
        profile = RegionProfile(
            "test",
            (2560, 1440),
            {
                "relic_choice_title": Rect(260, 62, 220, 60),
                "relic_choice_card_1": Rect(485, 330, 480, 750),
                "relic_choice_card_2": Rect(1040, 330, 480, 750),
                "relic_choice_card_3": Rect(1593, 330, 480, 750),
                "relic_choice_confirm_button": Rect(1080, 1158, 400, 82),
            },
        )
        texts = [
            RegionText("relic_choice_card_1_name", "\u4ee3\u6551\u62e8\u8005\u7684\u624b", 0.6),  # garbled, no score
            RegionText("relic_choice_card_2_name", "\u53e4\u4ee3\u6551\u63f4\u8005\u7684\u5e3d\u5b50", 0.9),
            RegionText("relic_choice_card_2_score", "8", 0.9),
            RegionText("relic_choice_card_3_name", "\u53e4\u4ee3\u6551\u63f4\u8005\u7684\u9879\u94fe", 0.9),
            RegionText("relic_choice_card_3_score", "8", 0.9),
        ]

        choice = parse_relic_choice(texts, profile)

        self.assertEqual(len(choice.options), 3)
        self.assertEqual(choice.options[0].name, "\u4ee3\u6551\u62e8\u8005\u7684\u624b")

    def test_parse_initial_relic_choice_sets_fixed_cuckoo_clock(self) -> None:
        profile = _initial_relic_profile()
        choice = parse_relic_choice(_initial_relic_texts(), profile)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.fixed_name, "annoying_cuckoo_clock")
        self.assertEqual(choice.options[1].target, profile.regions["relic_choice_card_2"])

    def test_parse_selected_initial_relic_choice_sets_selected_name_when_confirm_button_is_blue(self) -> None:
        profile = _initial_relic_profile()
        image = Image.new("RGB", profile.resolution, (30, 30, 30))
        button = profile.regions["relic_choice_confirm_button"]
        image.paste((45, 140, 225), (button.x, button.y, button.x + button.width, button.y + button.height))
        choice = parse_relic_choice(_initial_relic_texts(), profile, image)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.fixed_name, "annoying_cuckoo_clock")
        self.assertEqual(choice.selected_name, "annoying_cuckoo_clock")

    # ---- training hub ----
    def test_parse_training_hub_reads_status(self) -> None:
        profile, texts = _training_hub_fixture()
        status = parse_training_hub(texts, profile)
        self.assertIsNotNone(status)
        self.assertEqual(status.turn_label, "3\u4e0a\u65ec")
        self.assertEqual(status.coins, 48)
        self.assertIsNotNone(status.training_button)
        self.assertIsNotNone(status.commission_button)
        self.assertIsNotNone(status.rest_button)

    def test_parse_training_hub_detects_red_commission_alert(self) -> None:
        profile, texts = _training_hub_fixture()
        alert = Rect(200, 20, 80, 40)
        regions = dict(profile.regions)
        regions["training_hub_commission_alert"] = alert
        profile = RegionProfile(profile.name, profile.resolution, regions)
        image = Image.new("RGB", profile.resolution, (30, 30, 30))
        image.paste((220, 40, 40), (alert.x, alert.y, alert.x + alert.width, alert.y + alert.height))

        status = parse_training_hub(texts, profile, image)

        self.assertIsNotNone(status)
        self.assertTrue(status.has_commission_alert)

    def test_parse_training_hub_detects_commission_alert_text(self) -> None:
        profile, texts = _training_hub_fixture()
        texts.append(RegionText("training_hub_commission_alert", "\u53d7\u7406\u8ba8\u4f10\u59d4\u6258\uff01", 0.94))

        status = parse_training_hub(texts, profile)

        self.assertIsNotNone(status)
        self.assertTrue(status.has_commission_alert)

    def test_parse_training_hub_detects_skill_available_text(self) -> None:
        profile, texts = _training_hub_fixture()
        skill_button = Rect(1710, 1350, 220, 80)
        profile.regions["training_hub_nav_potential"] = skill_button
        texts.append(RegionText("training_hub_skill_available", "\u53ef\u4e60\u5f97", 0.95))

        status = parse_training_hub(texts, profile)

        self.assertIsNotNone(status)
        self.assertTrue(status.can_learn_skill)
        self.assertEqual(status.skill_button, skill_button)

    def test_parse_training_hub_detects_shop_alert_text(self) -> None:
        profile, texts = _training_hub_fixture()
        shop_button = Rect(1750, 665, 650, 180)
        profile.regions["training_hub_action_shop"] = shop_button
        texts.append(RegionText("training_hub_shop_alert", "\u5168\u65b0\u5546\u54c1\u5230\u8d27\uff01", 0.95))

        status = parse_training_hub(texts, profile)

        self.assertIsNotNone(status)
        self.assertTrue(status.has_shop_alert)
        self.assertEqual(status.shop_button, shop_button)

    def test_parse_training_hub_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"training_hub_action_training": Rect(1750, 450, 650, 180)})
        self.assertIsNone(parse_training_hub([RegionText("other", "nothing", 0.9)], profile))

    def test_parse_training_hub_detects_dday_battle_and_trading_buttons(self) -> None:
        # On 评鉴战日 the hub swaps 训练/委托/休息 for 评鉴战(top)+交易(bottom). parse must
        # surface BOTH buttons so the policy goes 交易 first, then 评鉴战.
        profile, texts = _training_hub_fixture()
        rb = Rect(2160, 650, 260, 75)
        tr = Rect(2180, 778, 240, 60)
        profile.regions["training_hub_rating_battle"] = rb
        profile.regions["training_hub_trading"] = tr
        texts.append(RegionText("training_hub_rating_battle", "评鉴战", 0.8))
        texts.append(RegionText("training_hub_trading", "交易", 0.99))
        status = parse_training_hub(texts, profile)
        self.assertEqual(status.rating_battle_button, rb)
        self.assertEqual(status.trading_button, tr)

    def test_parse_training_hub_normal_has_no_dday_buttons(self) -> None:
        # Normal hub (button area reads 训练/委托/休息, not 评鉴战/交易) -> no D-DAY buttons.
        profile, texts = _training_hub_fixture()
        profile.regions["training_hub_rating_battle"] = Rect(2160, 650, 260, 75)
        profile.regions["training_hub_trading"] = Rect(2180, 778, 240, 60)
        texts.append(RegionText("training_hub_rating_battle", "训练", 0.9))
        texts.append(RegionText("training_hub_trading", "休息", 0.9))
        status = parse_training_hub(texts, profile)
        self.assertIsNone(status.rating_battle_button)
        self.assertIsNone(status.trading_button)

    # ---- training select ----
    def test_parse_training_select_reads_five_choices(self) -> None:
        profile, texts = _training_select_fixture()
        choices = parse_training_select(texts, profile)
        self.assertIsNotNone(choices)
        self.assertEqual(len(choices), 5)
        names = {c.name for c in choices}
        self.assertEqual(names, {"power", "stamina", "guts", "wisdom", "speed"})
        power = next(c for c in choices if c.name == "power")
        self.assertEqual(power.fail_rate, 12)
        self.assertEqual(power.stat_gain, 18)

    def test_parse_training_select_falls_back_to_full_card_text(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"training_select_card_power": Rect(1750, 300, 650, 160), "training_select_confirm_button": Rect(2040, 1318, 470, 75)})
        texts = [RegionText("training_select_card_power", "\u529b\u91cf\u8bad\u7ec3 Lv.1 \u5931\u8d25\u73870%", 0.96)]

        choices = parse_training_select(texts, profile)

        self.assertIsNotNone(choices)
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0].name, "power")
        self.assertEqual(choices[0].fail_rate, 0)

    def test_parse_training_select_protection_maps_to_distinct_name(self) -> None:
        # 保护训练 (protection) must map to its own card slot ('speed'), not collide
        # with 韧性训练 ('guts'), so all five cards resolve to distinct names.
        profile = RegionProfile(
            "test",
            (2560, 1440),
            {
                "training_select_card_guts": Rect(1750, 635, 650, 112),
                "training_select_card_speed": Rect(1750, 929, 650, 112),
                "training_select_confirm_button": Rect(2040, 1318, 470, 75),
            },
        )
        texts = [
            RegionText("training_select_card_guts_name", "韧性训练", 0.9),
            RegionText("training_select_card_speed_name", "保护训练", 0.9),
        ]

        choices = parse_training_select(texts, profile)

        names = {c.name for c in choices or []}
        self.assertEqual(names, {"guts", "speed"})

    def test_parse_training_select_ignores_non_percent_digits_in_card(self) -> None:
        # Decorative glyphs that OCR as a long integer must not be read as a fail rate.
        profile = RegionProfile(
            "test",
            (2560, 1440),
            {
                "training_select_card_wisdom": Rect(1750, 780, 650, 114),
                "training_select_confirm_button": Rect(2040, 1318, 470, 75),
            },
        )
        texts = [RegionText("training_select_card_wisdom", "集中训练 10000000008 Lv.1", 0.8)]

        choices = parse_training_select(texts, profile)

        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0].name, "wisdom")
        self.assertEqual(choices[0].fail_rate, 0)

    def test_parse_training_select_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_training_select([RegionText("x", "y", 0.5)], profile))

    # ---- rest submenu ----
    def test_parse_rest_submenu_reads_options(self) -> None:
        profile, texts = _rest_submenu_fixture()
        rest = parse_rest_submenu(texts, profile)
        self.assertIsNotNone(rest)
        self.assertEqual(rest.coins, 55)
        self.assertTrue(rest.has_meditation_room)
        self.assertEqual(rest.rough_sleep, profile.regions["rest_submenu_option_1"])

    def test_parse_rest_submenu_detects_no_meditation(self) -> None:
        profile, texts = _rest_submenu_fixture(meditation_label="")
        rest = parse_rest_submenu(texts, profile)
        self.assertIsNotNone(rest)
        self.assertFalse(rest.has_meditation_room)

    def test_parse_rest_submenu_falls_back_to_fixed_layout_without_ocr(self) -> None:
        profile, _texts = _rest_submenu_fixture()
        rest = parse_rest_submenu([], profile)
        self.assertIsNotNone(rest)
        self.assertTrue(rest.has_meditation_room)
        self.assertEqual(rest.rough_sleep, profile.regions["rest_submenu_option_1"])
        self.assertEqual(rest.meditation_room, profile.regions["rest_submenu_option_3"])

    def test_parse_rest_submenu_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_rest_submenu([RegionText("x", "y", 0.5)], profile))

    # ---- event choice ----
    def test_parse_event_choice_reads_options(self) -> None:
        profile, texts = _event_choice_fixture()
        options = parse_event_choice(texts, profile)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 3)
        self.assertIn("stamina recover 20", options[0].text)

    def test_parse_event_choice_falls_back_to_full_option_text(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {"event_choice_title": Rect(330, 245, 400, 118), "event_choice_option_1": Rect(1720, 700, 760, 100)})
        options = parse_event_choice([RegionText("event_choice_title", "\u65c5\u7a0b\u4e8b\u4ef6", 0.92), RegionText("event_choice_option_1", "\u4ed8\u94b1\u8d2d\u4e70 50", 1.0)], profile)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].text, "\u4ed8\u94b1\u8d2d\u4e70 50")

    def test_parse_event_choice_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_event_choice([RegionText("x", "y", 0.5)], profile))

    # ---- commission select ----
    def test_parse_commission_select_reads_options(self) -> None:
        profile, texts = _commission_select_fixture()
        choice = parse_commission_select(texts, profile)
        self.assertIsInstance(choice, CommissionChoice)
        self.assertEqual(len(choice.options), 2)
        self.assertEqual(choice.options[0].name, "short_patrol")
        self.assertEqual(choice.options[0].rank, "C")

    def test_parse_commission_select_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_commission_select([RegionText("x", "y", 0.5)], profile))

    # ---- shop ----
    def test_parse_shop_reads_items(self) -> None:
        profile, texts = _shop_fixture()
        scene = parse_shop(texts, profile)
        self.assertIsNotNone(scene)
        self.assertEqual(len(scene.items), 2)
        self.assertEqual(scene.items[1].name, "\u9ad8\u7ea7\u8bad\u7ec3\u4e66")
        self.assertEqual(scene.items[1].price, 110)

    def test_parse_shop_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_shop([RegionText("x", "y", 0.5)], profile))

    def test_parse_shop_returns_item_per_row_even_without_name_price(self) -> None:
        # Journey Trading's right-side list OCRs unreliably, but the buy decision
        # keys off each item's effect (read by clicking the row), so parse must
        # still return one clickable item per defined row when name/price are blank.
        profile = RegionProfile(
            "test",
            (2560, 1440),
            {
                "shop_item_1": Rect(2240, 552, 260, 62),
                "shop_item_2": Rect(2240, 707, 260, 62),
                "shop_item_3": Rect(2240, 862, 260, 62),
            },
        )
        scene = parse_shop([], profile)
        self.assertIsNotNone(scene)
        self.assertEqual(len(scene.items), 3)
        self.assertEqual(scene.items[0].target, Rect(2240, 552, 260, 62))
        self.assertEqual(scene.items[2].target, Rect(2240, 862, 260, 62))

    # ---- region move ----
    def test_parse_region_move_detects_button(self) -> None:
        profile, texts = _region_move_fixture()
        rect = parse_region_move(texts, profile)
        self.assertIsNotNone(rect)

    def test_parse_region_move_returns_none_without_text(self) -> None:
        profile, texts = _region_move_fixture(button_text="other")
        rect = parse_region_move(texts, profile)
        self.assertIsNone(rect)

    # ---- post training ----
    def test_parse_post_training_reads_result(self) -> None:
        profile, texts = _post_training_fixture()
        result = parse_post_training(texts, profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.stat_gain_value, 10)
        self.assertIn("\u63d0\u5347", result.result_text or "")

    def test_parse_post_training_reads_success_animation(self) -> None:
        continue_area = Rect(980, 1040, 700, 155)
        profile = RegionProfile(
            "test",
            (2560, 1440),
            {
                "post_training_title": Rect(1000, 40, 650, 95),
                "post_training_success_text": continue_area,
                "post_training_continue_area": continue_area,
            },
        )
        result = parse_post_training(
            [
                RegionText("post_training_title", "\u529b\u91cf\u8bad\u7ec3 Lv.1", 0.9),
                RegionText("post_training_success_text", "\u8bad\u7ec3\u6210\u529f!", 0.9),
            ],
            profile,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.skip_button, continue_area)
        self.assertIn("\u8bad\u7ec3\u6210\u529f", result.result_text or "")

    def test_parse_post_training_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_post_training([RegionText("x", "y", 0.5)], profile))

    # ---- training direction ----
    def test_parse_training_direction_reads_three_options(self) -> None:
        profile, texts = _training_direction_fixture()
        options = parse_training_direction(texts, profile)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 3)
        self.assertIn("\u653b\u51fb", options[0].text)

    def test_parse_training_direction_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_training_direction([RegionText("x", "y", 0.5)], profile))

    # ---- battle ----
    def test_parse_battle_reads_skip_button(self) -> None:
        profile, texts = _battle_fixture()
        scene = parse_battle(texts, profile)
        self.assertIsNotNone(scene)
        self.assertIsInstance(scene, BattleScene)
        self.assertEqual(scene.skip_button, profile.regions["battle_skip_button"])
        self.assertFalse(scene.confirm_active)

    def test_parse_battle_prefers_entry_button_when_present(self) -> None:
        profile, texts = _battle_fixture()
        entry = Rect(2165, 630, 350, 130)
        profile.regions["battle_entry_button"] = entry

        scene = parse_battle(texts, profile)

        self.assertIsNotNone(scene)
        self.assertEqual(scene.skip_button, entry)

    def test_parse_battle_detects_active_accept_button(self) -> None:
        profile, texts = _battle_fixture()
        accept = Rect(2010, 1255, 370, 105)
        profile.regions["battle_accept_button"] = accept
        image = Image.new("RGB", (2560, 1440), "black")
        crop = Image.new("RGB", (accept.width, accept.height), (50, 130, 220))
        image.paste(crop, (accept.x, accept.y))

        scene = parse_battle(texts, profile, image)

        self.assertIsNotNone(scene)
        self.assertEqual(scene.confirm_button, accept)
        self.assertTrue(scene.confirm_active)

    def test_parse_battle_accept_button_works_without_ocr_anchor(self) -> None:
        profile, _texts = _battle_fixture()
        accept = Rect(2010, 1255, 370, 105)
        profile.regions["battle_accept_button"] = accept
        image = Image.new("RGB", (2560, 1440), "black")
        crop = Image.new("RGB", (accept.width, accept.height), (50, 130, 220))
        image.paste(crop, (accept.x, accept.y))

        scene = parse_battle([], profile, image)

        self.assertIsNotNone(scene)
        self.assertEqual(scene.confirm_button, accept)
        self.assertTrue(scene.confirm_active)

    def test_parse_battle_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_battle([RegionText("x", "y", 0.5)], profile))

    def test_parse_battle_rating_confirm_picks_skip_battle_button(self) -> None:
        # 基础评鉴战 entry confirm: pick 跳过战斗 (skip → instant result), never
        # 开始委托 (which actually fights). confirm_active must stay False so
        # decide_battle clicks the skip button, not a confirm.
        skip = Rect(1010, 1010, 180, 70)
        profile = RegionProfile("test", (2560, 1440), {"battle_skip_battle_button": skip})
        texts = [
            RegionText("battle_skip_battle_button", "跳过战斗", 1.0),
            RegionText("battle_confirm_title", "基础评鉴战", 0.99),
        ]
        scene = parse_battle(texts, profile)
        self.assertIsNotNone(scene)
        self.assertEqual(scene.skip_button, skip)
        self.assertFalse(scene.confirm_active)

    def test_parse_battle_skip_confirm_dialog_clicks_blue_confirm(self) -> None:
        # 点底层「跳过战斗」后弹二次确认框(标题跳过战斗 / "确定要跳过评鉴战斗吗?" /
        # 取消 + 蓝色「跳过战斗」)。必须点框内蓝色「跳过战斗」确认, 而不是又点被遮住的
        # 底层按钮(否则死循环)。底层「跳过战斗」此时仍透出可被 OCR 读到。
        confirm = Rect(1385, 912, 170, 58)
        profile = RegionProfile(
            "test",
            (2560, 1440),
            {
                "battle_skip_confirm_button": confirm,
                "battle_skip_confirm_cancel": Rect(1010, 912, 160, 58),
                "battle_skip_battle_button": Rect(1010, 1010, 180, 70),
            },
        )
        texts = [
            RegionText("battle_skip_confirm_cancel", "取消", 0.98),
            RegionText("battle_skip_confirm_button", "跳过战斗", 0.9),
            RegionText("battle_skip_battle_button", "跳过战斗", 0.99),  # 底层透出
        ]
        scene = parse_battle(texts, profile)
        self.assertIsNotNone(scene)
        self.assertEqual(scene.skip_button, confirm)
        self.assertFalse(scene.confirm_active)

    # ---- skill select ----
    def test_parse_skill_select_reads_options(self) -> None:
        profile, texts = _skill_select_fixture()
        options = parse_skill_select(texts, profile)
        self.assertIsNotNone(options)
        self.assertEqual(len(options), 3)
        self.assertIsInstance(options[0], SkillOption)
        self.assertEqual(options[0].name, "\u653b\u51fb\u6280\u80fd1")
        self.assertEqual(options[0].effect, "\u653b\u51fb+5")
        self.assertEqual(options[0].target, profile.regions["skill_select_option_1"])

    def test_parse_skill_select_uses_learn_button_and_cost(self) -> None:
        profile, texts = _skill_select_fixture()
        button = Rect(1840, 395, 310, 90)
        profile.regions["skill_select_option_1_button"] = button
        profile.regions["skill_select_option_1_cost"] = Rect(1975, 415, 160, 60)
        texts.append(RegionText("skill_select_option_1_cost", "10%SALE 90", 0.95))

        options = parse_skill_select(texts, profile)

        self.assertIsNotNone(options)
        self.assertEqual(options[0].target, button)
        self.assertEqual(options[0].cost, 90)

    def test_parse_skill_select_returns_none_without_anchor(self) -> None:
        profile = RegionProfile("test", (2560, 1440), {})
        self.assertIsNone(parse_skill_select([RegionText("x", "y", 0.5)], profile))

    # ---- region reader ----
    def test_region_reader_can_skip_large_regions(self) -> None:
        profile = RegionProfile("test", (100, 100), {"game_client": Rect(0, 0, 100, 100), "title": Rect(0, 0, 20, 10)})
        ocr = CountingOcr()
        reader = RegionOcrReader(profile, ocr)
        results = reader.read_all(Image.new("RGB", profile.resolution), max_area=500)
        self.assertEqual([result.name for result in results], ["title"])
        self.assertEqual(ocr.names_seen, [(20, 10)])

    def test_region_reader_can_read_matching_prefixes_only(self) -> None:
        profile = RegionProfile("test", (100, 100), {"dialogue_intro_skip_button": Rect(0, 0, 20, 10), "relic_choice_title": Rect(0, 10, 20, 10)})
        ocr = CountingOcr()
        reader = RegionOcrReader(profile, ocr)
        results = reader.read_prefixes(Image.new("RGB", profile.resolution), ["relic_choice"])
        self.assertEqual([result.name for result in results], ["relic_choice_title"])
        self.assertEqual(ocr.names_seen, [(20, 10)])

    def test_region_reader_can_read_text_like_regions_only(self) -> None:
        profile = RegionProfile("test", (100, 100), {"game_client": Rect(0, 0, 100, 100), "relic_choice_card_1": Rect(0, 0, 20, 20), "relic_choice_card_1_name": Rect(0, 0, 20, 10), "relic_choice_card_1_score": Rect(0, 10, 20, 10)})
        ocr = CountingOcr()
        reader = RegionOcrReader(profile, ocr)
        results = reader.read_ocr_regions(Image.new("RGB", profile.resolution))
        self.assertEqual([result.name for result in results], ["relic_choice_card_1_name", "relic_choice_card_1_score"])
        self.assertEqual(ocr.names_seen, [(20, 10), (20, 10)])


# ---- helpers ----


class CountingOcr:
    def __init__(self) -> None:
        self.names_seen: list[tuple[int, int]] = []

    def read_text(self, image: Image.Image) -> OcrResult:
        self.names_seen.append(image.size)
        return OcrResult(text="ok", confidence=1.0)


def _initial_relic_profile() -> RegionProfile:
    return RegionProfile("test", (2560, 1440), {"relic_choice_title": Rect(260, 62, 220, 60), "relic_choice_card_1": Rect(485, 330, 480, 750), "relic_choice_card_2": Rect(1040, 330, 480, 750), "relic_choice_card_3": Rect(1593, 330, 480, 750), "relic_choice_confirm_button": Rect(1080, 1158, 400, 82)})


def _initial_relic_texts() -> list[RegionText]:
    return [RegionText("relic_choice_title", "\u9009\u62e9\u5956\u52b1", 0.98), RegionText("relic_choice_card_1_name", "\u8f6f\u7ef5\u7ef5\u7684\u73a9\u5076\u670b\u53cb", 0.9), RegionText("relic_choice_card_1_score", "12", 0.9), RegionText("relic_choice_card_2_name", "\u70e6\u4eba\u7684\u5e03\u8c37\u9e1f\u65f6\u949f", 0.9), RegionText("relic_choice_card_2_score", "12", 0.9), RegionText("relic_choice_card_3_name", "\u5e73\u8861\u7684\u5929\u79e4", 0.9), RegionText("relic_choice_card_3_score", "12", 0.9)]


def _blessing_setup_profile() -> RegionProfile:
    return RegionProfile("test", (2560, 1440), {"blessing_setup_anchor_title": Rect(330, 66, 230, 58), "blessing_slot_1": Rect(958, 728, 250, 270), "blessing_slot_2": Rect(2070, 424, 250, 270), "blessing_auto_equip_button": Rect(2110, 1220, 265, 65), "blessing_confirm_button": Rect(2108, 1305, 360, 75)})


def _training_hub_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"training_hub_anchor_title": Rect(330, 66, 290, 60), "training_hub_distance": Rect(46, 54, 255, 135), "training_hub_turn_label": Rect(330, 126, 290, 60), "training_hub_coin_count": Rect(1420, 58, 120, 55), "training_hub_rank_label": Rect(98, 195, 395, 48), "training_hub_potential_points": Rect(98, 960, 395, 48), "training_hub_action_training": Rect(1750, 450, 650, 180), "training_hub_action_commission": Rect(1750, 665, 650, 180), "training_hub_action_rest": Rect(1750, 880, 650, 180)})
    texts = [RegionText("training_hub_anchor_title", "\u53c2\u52a0\u8bc4\u9274\u6218", 0.95), RegionText("training_hub_distance", "\u8ddd\u79bb\u76ee\u6807 6", 0.9), RegionText("training_hub_turn_label", "3\u4e0a\u65ec", 0.9), RegionText("training_hub_coin_count", "48", 0.92), RegionText("training_hub_rank_label", "RANK 13", 0.85), RegionText("training_hub_potential_points", "21", 0.88)]
    return profile, texts


def _training_select_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"training_select_card_power": Rect(1750, 300, 650, 160), "training_select_card_stamina": Rect(1750, 480, 650, 160), "training_select_card_guts": Rect(1750, 660, 650, 160), "training_select_card_wisdom": Rect(1750, 840, 650, 160), "training_select_card_speed": Rect(1750, 1020, 650, 160), "training_select_confirm_button": Rect(2040, 1318, 470, 75)})
    texts = [RegionText("training_select_card_power_name", "\u529b\u91cf\u8bad\u7ec3", 0.9), RegionText("training_select_card_power_fail_rate", "12%", 0.9), RegionText("training_select_stat_gain_power", "18", 0.9), RegionText("training_select_card_stamina_name", "\u4f53\u529b\u8bad\u7ec3", 0.9), RegionText("training_select_card_stamina_fail_rate", "5%", 0.9), RegionText("training_select_stat_gain_stamina", "10", 0.9), RegionText("training_select_card_guts_name", "\u97e7\u6027\u8bad\u7ec3", 0.9), RegionText("training_select_card_guts_fail_rate", "0%", 0.9), RegionText("training_select_stat_gain_guts", "8", 0.9), RegionText("training_select_card_wisdom_name", "\u96c6\u4e2d\u8bad\u7ec3", 0.9), RegionText("training_select_card_wisdom_fail_rate", "0%", 0.9), RegionText("training_select_stat_gain_wisdom", "14", 0.9), RegionText("training_select_card_speed_name", "\u901f\u5ea6\u8bad\u7ec3", 0.9), RegionText("training_select_card_speed_fail_rate", "0%", 0.9), RegionText("training_select_stat_gain_speed", "12", 0.9)]
    return profile, texts


def _rest_submenu_fixture(meditation_label: str = "\u51a5\u60f3\u5ba4") -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"rest_submenu_coin_count": Rect(1420, 58, 120, 55), "rest_submenu_option_1": Rect(700, 400, 1160, 180), "rest_submenu_option_2": Rect(700, 610, 1160, 180), "rest_submenu_option_3": Rect(700, 820, 1160, 180)})
    texts = [RegionText("rest_submenu_coin_count", "55", 0.9), RegionText("rest_submenu_option_2_label", "\u9732\u5bbf", 0.9), RegionText("rest_submenu_option_2_cost", "30\u91d1\u5e01", 0.9), RegionText("rest_submenu_option_3_label", meditation_label, 0.9), RegionText("rest_submenu_option_3_cost", "60\u91d1\u5e01", 0.9)]
    return profile, texts


def _event_choice_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"event_choice_title": Rect(330, 245, 400, 118), "event_choice_option_1": Rect(700, 650, 1160, 120), "event_choice_option_2": Rect(700, 800, 1160, 120), "event_choice_option_3": Rect(700, 950, 1160, 120)})
    texts = [RegionText("event_choice_title", "\u65c5\u7a0b\u4e8b\u4ef6", 0.92), RegionText("event_choice_option_1_text", "stamina recover 20", 0.88), RegionText("event_choice_option_2_text", "mood up", 0.88), RegionText("event_choice_option_3_text", "speed +12", 0.88)]
    return profile, texts


def _commission_select_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"commission_select_anchor_title": Rect(330, 66, 290, 60), "commission_select_option_1": Rect(600, 350, 1360, 140), "commission_select_option_2": Rect(600, 520, 1360, 140)})
    texts = [RegionText("commission_select_option_1_name", "short_patrol", 0.9), RegionText("commission_select_option_1_rank", "C", 0.9), RegionText("commission_select_option_2_name", "highland_training", 0.9), RegionText("commission_select_option_2_rank", "B", 0.9)]
    return profile, texts


def _shop_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"shop_item_1": Rect(600, 350, 1360, 120), "shop_item_2": Rect(600, 500, 1360, 120)})
    texts = [RegionText("shop_item_1_name", "\u4f53\u529b\u836f", 0.9), RegionText("shop_item_1_price", "75", 0.9), RegionText("shop_item_2_name", "\u9ad8\u7ea7\u8bad\u7ec3\u4e66", 0.9), RegionText("shop_item_2_price", "110", 0.9)]
    return profile, texts


def _region_move_fixture(button_text: str = "\u79fb\u52a8") -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"region_move_button": Rect(1750, 800, 650, 200), "region_move_button_text": Rect(1770, 830, 610, 80)})
    texts = [RegionText("region_move_button_text", button_text, 0.92)]
    return profile, texts


def _post_training_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"post_training_result_text": Rect(640, 900, 1280, 120), "post_training_stat_gain_value": Rect(1120, 880, 320, 80), "post_training_skip_button": Rect(1855, 54, 78, 65)})
    texts = [RegionText("post_training_result_text", "\u7f57\u838e\u8389\u4e9a\u7684\u529b\u91cf\u63d0\u5347\u4e86\u3002", 0.9), RegionText("post_training_stat_gain_value", "+10", 0.9)]
    return profile, texts


def _training_direction_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {"training_direction_title": Rect(330, 245, 290, 118), "training_direction_option_1": Rect(1750, 400, 650, 120), "training_direction_option_2": Rect(1750, 560, 650, 120), "training_direction_option_3": Rect(1750, 720, 650, 120)})
    texts = [RegionText("training_direction_title", "\u8bad\u7ec3\u7684\u65b9\u5411\u6027", 0.92), RegionText("training_direction_option_1_text", "\u5bf9\u653b\u51fb\u6709\u5e2e\u52a9\u7684\u8bad\u7ec3\u6559\u6750", 0.88), RegionText("training_direction_option_2_text", "\u5bf9\u751f\u5b58\u6709\u5e2e\u52a9\u7684\u8bad\u7ec3\u6559\u6750", 0.88), RegionText("training_direction_option_3_text", "\u6709\u52a9\u4e8e\u5e94\u5bf9\u5404\u79cd\u72b6\u51b5\u7684\u8bad\u7ec3\u6559\u6750", 0.88)]
    return profile, texts


def _battle_fixture(skip_text: str = "\u8df3\u8fc7\u6218\u6597") -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {
        "battle_title": Rect(330, 66, 290, 60),
        "battle_skip_button": Rect(2350, 55, 145, 60),
        "battle_skip_button_text": Rect(2360, 62, 125, 45),
        "battle_confirm_button": Rect(1290, 941, 357, 75),
    })
    texts = [RegionText("battle_title", "\u8bc4\u9274\u6218", 0.92), RegionText("battle_skip_button_text", skip_text, 0.9)]
    return profile, texts


def _skill_select_fixture() -> tuple[RegionProfile, list[RegionText]]:
    profile = RegionProfile("test", (2560, 1440), {
        "skill_select_title": Rect(330, 66, 290, 60),
        "skill_select_option_1": Rect(600, 300, 1360, 100),
        "skill_select_option_2": Rect(600, 420, 1360, 100),
        "skill_select_option_3": Rect(600, 540, 1360, 100),
    })
    texts = [
        RegionText("skill_select_title", "\u6f5c\u8d28", 0.92),
        RegionText("skill_select_option_1_name", "\u653b\u51fb\u6280\u80fd1", 0.9),
        RegionText("skill_select_option_1_effect", "\u653b\u51fb+5", 0.88),
        RegionText("skill_select_option_2_name", "\u9632\u5fa1\u6280\u80fd2", 0.9),
        RegionText("skill_select_option_2_effect", "\u9632\u5fa1+3", 0.88),
        RegionText("skill_select_option_3_name", "\u901f\u5ea6\u6280\u80fd3", 0.9),
    ]
    return profile, texts


if __name__ == "__main__":
    unittest.main()
