import unittest

from starsavior_trainer.fixtures import demo_observations, demo_state
from starsavior_trainer.models import (
    Action,
    BlessingChoice,
    BlessingOption,
    BlessingSetup,
    BlessingSlot,
    CharacterOption,
    CharacterSelect,
    CommissionChoice,
    CommissionOption,
    ConfirmDialog,
    DialogueScene,
    EventOption,
    EventFastForwardSetting,
    GameState,
    JourneyStart,
    Observation,
    Rect,
    RelicChoice,
    RelicOption,
    Screen,
    SkillOption,
    TrainingChoice,
    TrainingHubStatus,
)
from starsavior_trainer.policy import TrainerPolicy


class TrainerPolicyTest(unittest.TestCase):
    def test_demo_policy_produces_actions_for_all_observations(self) -> None:
        policy = TrainerPolicy()
        state = demo_state()

        actions = [policy.decide(state, observation) for observation in demo_observations()]

        self.assertTrue(all(isinstance(action, Action) for action in actions))
        self.assertEqual(actions[0].kind, "click")
        self.assertEqual(actions[-1].kind, "pause")

    def test_low_confidence_pauses_before_screen_specific_logic(self) -> None:
        action = TrainerPolicy().decide(demo_state(), Observation(Screen.INITIAL, 0.1))

        self.assertEqual(action.kind, "pause")
        self.assertIn("low screen confidence", action.reason)

    def test_initial_screen_uses_route_select_start_button_region(self) -> None:
        action = TrainerPolicy().decide(demo_state(), Observation(Screen.INITIAL, 0.95))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, Rect(2040, 1318, 470, 75))

    def test_character_select_confirms_selected_character(self) -> None:
        selection = CharacterSelect(
            options=[
                CharacterOption("beier_lisi", "A", 4, "focus", True, Rect(1624, 202, 363, 96)),
            ],
            confirm_button=Rect(1629, 1046, 357, 58),
            selected_name="beier_lisi",
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.CHARACTER_SELECT, 0.95, selection))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, selection.confirm_button)
        self.assertIn("confirm selected character", action.reason)

    def test_character_select_clicks_desired_character_when_visible(self) -> None:
        opt1 = CharacterOption("萍贝塔", None, None, None, False, Rect(2030, 250, 458, 122))
        opt2 = CharacterOption("克莱儿", None, None, None, False, Rect(2030, 394, 458, 122))
        selection = CharacterSelect(
            options=[opt1, opt2],
            confirm_button=Rect(2038, 1305, 448, 75),
            selected_name=None,
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="克莱儿"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, opt2.target)
        self.assertIn("克莱儿", action.reason)

    def test_character_select_confirms_when_desired_is_already_selected(self) -> None:
        confirm = Rect(2038, 1305, 448, 75)
        opt = CharacterOption("克莱儿", None, None, None, True, Rect(2030, 394, 458, 122))
        selection = CharacterSelect(
            options=[opt],
            confirm_button=confirm,
            selected_name="克莱儿",
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="克莱儿"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, confirm)
        self.assertIn("confirm desired character", action.reason)

    def test_character_select_tolerant_match_ignores_dot_prefix(self) -> None:
        # OCR drops the rank prefix and middle dot, yielding only the tail name;
        # the tolerant fallback should still resolve the desired character.
        opt = CharacterOption("莉丝", None, None, None, False, Rect(2030, 394, 458, 122))
        selection = CharacterSelect(
            options=[opt],
            confirm_button=Rect(2038, 1305, 448, 75),
            selected_name=None,
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="贝尔·莉丝"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, opt.target)

    def test_character_select_prefers_exact_over_substring_match(self) -> None:
        # Both a costume variant and the base name are visible; an exact match
        # must win so picking 芙蕾 does not select 兔女郎芙蕾.
        variant = CharacterOption("兔女郎芙蕾", None, None, None, False, Rect(2030, 250, 458, 122))
        base = CharacterOption("芙蕾", None, None, None, False, Rect(2030, 394, 458, 122))
        selection = CharacterSelect(
            options=[variant, base],
            confirm_button=Rect(2038, 1305, 448, 75),
            selected_name=None,
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="芙蕾"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.target, base.target)

    def test_character_select_scrolls_when_desired_not_visible(self) -> None:
        # List has 7 entries, none match the desired character
        opts = [
            CharacterOption(f"char_{i}", None, None, None, False, Rect(2030, 250 + i * 144, 458, 122))
            for i in range(7)
        ]
        selection = CharacterSelect(
            options=opts,
            confirm_button=Rect(2038, 1305, 448, 75),
            selected_name=None,
            can_scroll=True,
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="目标角色"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.kind, "scroll")
        self.assertLess(action.scroll_clicks, 0, "scroll direction should be down (negative)")
        self.assertIn("目标角色", action.reason)

    def test_character_select_pauses_when_desired_not_visible_and_cannot_scroll(self) -> None:
        # Fewer than 7 entries → list exhausted → pause instead of infinite scroll
        opt = CharacterOption("达娜", None, None, None, False, Rect(2030, 250, 458, 122))
        selection = CharacterSelect(
            options=[opt],
            confirm_button=Rect(2038, 1305, 448, 75),
            selected_name="达娜",
            can_scroll=False,
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="芙蕾"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.kind, "pause")
        self.assertIn("芙蕾", action.reason)

    def test_build_profile_changes_training_score(self) -> None:
        policy = TrainerPolicy()
        power = TrainingChoice("power", 10, "none", 0, Rect(0, 0, 10, 10))
        speed = TrainingChoice("speed", 20, "none", 0, Rect(0, 0, 10, 10))

        balanced = policy.decide_training([power, speed], GameState(build_profile="balanced"))
        focused = policy.decide_training([power, speed], GameState(build_profile="power_focus"))

        self.assertIn("speed", balanced.reason)
        self.assertIn("power", focused.reason)

    def test_training_selects_desired_card_when_not_yet_selected(self) -> None:
        # Desired training (power) is not the highlighted card → click it to select.
        confirm = Rect(2080, 1252, 400, 95)
        power = TrainingChoice("power", 0, "none", 0, Rect(1750, 338, 650, 112), selected=False, confirm_button=confirm)
        stamina = TrainingChoice("stamina", 0, "none", 0, Rect(1750, 487, 650, 112), selected=True, confirm_button=confirm)

        action = TrainerPolicy().decide_training([power, stamina], GameState(build_profile="power_focus"))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, power.target)
        self.assertIn("select", action.reason)

    def test_training_confirms_when_desired_card_already_selected(self) -> None:
        # Desired training is already highlighted → click the 训练 confirm button.
        confirm = Rect(2080, 1252, 400, 95)
        power = TrainingChoice("power", 0, "none", 0, Rect(1750, 338, 650, 112), selected=True, confirm_button=confirm)
        stamina = TrainingChoice("stamina", 0, "none", 0, Rect(1750, 487, 650, 112), selected=False, confirm_button=confirm)

        action = TrainerPolicy().decide_training([power, stamina], GameState(build_profile="power_focus"))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, confirm)
        self.assertIn("confirm", action.reason)

    def test_training_skips_overfailed_main_and_falls_to_next(self) -> None:
        # Main training (stamina) is selected but its fail rate exceeds the
        # threshold → it is excluded and the next viable card is selected instead.
        confirm = Rect(2080, 1252, 400, 95)
        stamina = TrainingChoice("stamina", 0, "none", 46, Rect(1750, 487, 650, 112), selected=True, confirm_button=confirm)
        guts = TrainingChoice("guts", 0, "none", 0, Rect(1750, 635, 650, 112), selected=False, confirm_button=confirm)

        action = TrainerPolicy().decide_training([stamina, guts], GameState(build_profile="stamina_tank"))

        self.assertEqual(action.target, guts.target)
        self.assertIn("guts", action.reason)

    def test_training_returns_to_hub_when_all_fail_rates_too_high(self) -> None:
        # Stamina exhausted: every training exceeds the fail-rate threshold. Instead
        # of pausing (which would get stuck), click the back arrow to return to the
        # hub, where the hub-level decision can route to rest.
        confirm = Rect(2080, 1252, 400, 95)
        back = Rect(90, 62, 55, 64)
        choices = [
            TrainingChoice(name, 0, "none", 46, Rect(1750, 338 + i * 148, 650, 112),
                           selected=(name == "power"), confirm_button=confirm, back_button=back)
            for i, name in enumerate(("power", "stamina", "guts", "wisdom", "speed"))
        ]

        action = TrainerPolicy().decide_training(choices, GameState(build_profile="power_focus"))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, back)
        self.assertNotEqual(action.kind, "pause")
        self.assertIn("rest", action.reason)

    def test_training_pauses_when_all_high_and_no_back_button(self) -> None:
        # Fallback: if the back button is unavailable, still pause (don't crash).
        choices = [
            TrainingChoice("power", 0, "none", 46, Rect(1750, 338, 650, 112)),
            TrainingChoice("stamina", 0, "none", 46, Rect(1750, 487, 650, 112)),
        ]

        action = TrainerPolicy().decide_training(choices, GameState(build_profile="power_focus"))

        self.assertEqual(action.kind, "pause")

    def test_hub_rests_after_training_bailout_then_resumes(self) -> None:
        # Full anti-loop flow: training bail-out sets the rest flag; the next hub
        # decision rests (not training); the following hub decision resumes training.
        policy = TrainerPolicy()
        state = GameState(build_profile="power_focus")
        back = Rect(90, 62, 55, 64)
        train_btn = Rect(1750, 450, 650, 180)
        rest_btn = Rect(1750, 880, 650, 180)
        hub = TrainingHubStatus(training_button=train_btn, rest_button=rest_btn)
        high = [
            TrainingChoice(n, 0, "none", 46, Rect(1750, 338, 650, 112), back_button=back)
            for n in ("power", "stamina")
        ]

        # 1) all training too risky -> bail back to hub, flag set
        bail = policy.decide_training(high, state)
        self.assertEqual(bail.target, back)
        self.assertTrue(policy._needs_rest)

        # 2) hub consumes the flag -> rest
        rest = policy.decide(state, Observation(Screen.TRAINING_HUB, 1.0, hub))
        self.assertEqual(rest.target, rest_btn)
        self.assertIn("rest", rest.reason)
        self.assertFalse(policy._needs_rest)

        # 3) flag cleared -> hub resumes normal training (no loop)
        resume = policy.decide(state, Observation(Screen.TRAINING_HUB, 1.0, hub))
        self.assertEqual(resume.target, train_btn)

    def test_event_attack_survival_branch_follows_build_profile(self) -> None:
        # 训练的方向性-style events: power builds take the attack option, stamina
        # builds take the survival option.
        attack = EventOption(text="对攻击有帮助的训练教材", target=Rect(1720, 798, 660, 92))
        survival = EventOption(text="对生存有帮助的训练教材", target=Rect(1720, 894, 660, 92))
        utility = EventOption(text="有助于应对各种状况的训练教材", target=Rect(1720, 990, 660, 92))
        options = [attack, survival, utility]
        policy = TrainerPolicy()

        power = policy.decide_event(options, GameState(build_profile="power_focus"))
        stamina = policy.decide_event(options, GameState(build_profile="stamina_tank"))

        self.assertEqual(power.target, attack.target)
        self.assertEqual(stamina.target, survival.target)

    def test_event_without_build_branch_uses_keyword_priority(self) -> None:
        # Non attack/survival events still fall back to keyword scoring.
        coins = EventOption(text="付钱购买。", target=Rect(0, 0, 10, 10))
        pass_by = EventOption(text="直接走过。", target=Rect(0, 20, 10, 10))
        action = TrainerPolicy().decide_event([coins, pass_by], GameState(build_profile="power_focus"))
        self.assertEqual(action.target, coins.target)

    def test_event_db_lookup_picks_recommended_option_per_build(self) -> None:
        # 神秘石像 in events.json: power_focus->1 (sword/power), stamina_tank->2 (flower/life).
        # The OCR'd title carries a noisy prefix; the fuzzy matcher must still resolve it.
        sword = EventOption("向持剑石像祈祷。", Rect(1720, 798, 660, 92), event_title="旅程事件 神秘石像")
        flower = EventOption("向持花石像祈祷。", Rect(1720, 894, 660, 92), event_title="旅程事件 神秘石像")
        none = EventOption("不祈祷。", Rect(1720, 990, 660, 92), event_title="旅程事件 神秘石像")
        options = [sword, flower, none]
        policy = TrainerPolicy()

        power = policy.decide_event(options, GameState(build_profile="power_focus"))
        stamina = policy.decide_event(options, GameState(build_profile="stamina_tank"))

        self.assertEqual(power.target, sword.target)
        self.assertIn("event db", power.reason)
        self.assertEqual(stamina.target, flower.target)

    def test_event_db_tolerates_ocr_character_errors_in_title(self) -> None:
        # 训练的方向 OCR'd as 川练的方向性 (训→川) must still match via fuzzy scoring.
        attack = EventOption("对攻击有帮助的训练教材", Rect(1720, 798, 660, 92), event_title="旅程事件 川练的方向性")
        survival = EventOption("对生存有帮助的训练教材", Rect(1720, 894, 660, 92), event_title="旅程事件 川练的方向性")
        utility = EventOption("有助于应对各种状况的训练教材", Rect(1720, 990, 660, 92), event_title="旅程事件 川练的方向性")
        options = [attack, survival, utility]

        power = TrainerPolicy().decide_event(options, GameState(build_profile="power_focus"))
        stamina = TrainerPolicy().decide_event(options, GameState(build_profile="stamina_tank"))

        self.assertEqual(power.target, attack.target)
        self.assertEqual(stamina.target, survival.target)

    def test_training_hub_uses_commission_alert_before_training(self) -> None:
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            commission_button=Rect(40, 40, 20, 20),
            rest_button=Rect(70, 70, 20, 20),
            has_commission_alert=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, hub.commission_button)
        self.assertIn("commission alert", action.reason)

    def test_training_hub_opens_skill_learning_when_available(self) -> None:
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            commission_button=Rect(40, 40, 20, 20),
            rest_button=Rect(70, 70, 20, 20),
            skill_button=Rect(100, 100, 20, 20),
            can_learn_skill=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, hub.skill_button)
        self.assertIn("skill learning", action.reason)

    def test_training_hub_opens_skill_learning_at_point_threshold(self) -> None:
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            skill_button=Rect(100, 100, 20, 20),
            potential_points=120,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.target, hub.skill_button)

    def test_training_hub_commission_alert_preempts_skill_learning(self) -> None:
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            commission_button=Rect(40, 40, 20, 20),
            skill_button=Rect(100, 100, 20, 20),
            has_commission_alert=True,
            can_learn_skill=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.target, hub.commission_button)

    def test_training_hub_opens_shop_when_goods_arrive(self) -> None:
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            shop_button=Rect(130, 130, 20, 20),
            has_shop_alert=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, hub.shop_button)
        self.assertIn("shop alert", action.reason)

    def test_training_hub_shop_alert_preempts_skill_learning(self) -> None:
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            skill_button=Rect(100, 100, 20, 20),
            shop_button=Rect(130, 130, 20, 20),
            can_learn_skill=True,
            has_shop_alert=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.target, hub.shop_button)

    def test_skill_select_uses_build_profile_keywords(self) -> None:
        options = [
            SkillOption("生命感知", cost=100, target=Rect(10, 10, 20, 20)),
            SkillOption("攻击感知", cost=90, target=Rect(40, 40, 20, 20)),
        ]

        action = TrainerPolicy().decide(
            GameState(build_profile="power_focus"),
            Observation(Screen.SKILL_SELECT, 0.95, options),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, options[1].target)
        self.assertIn("攻击感知", action.reason)

    def test_skill_select_avoids_learned_options(self) -> None:
        options = [
            SkillOption("已习得 攻击感知", cost=90, target=Rect(10, 10, 20, 20)),
            SkillOption("未习得 生命感知", cost=100, target=Rect(40, 40, 20, 20)),
        ]

        action = TrainerPolicy().decide(
            GameState(build_profile="power_focus"),
            Observation(Screen.SKILL_SELECT, 0.95, options),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, options[1].target)

    def test_blessing_setup_opens_first_empty_slot(self) -> None:
        setup = BlessingSetup(
            slots=[
                BlessingSlot(1, False, Rect(10, 10, 20, 20)),
                BlessingSlot(2, False, Rect(40, 40, 20, 20)),
            ],
            auto_equip_button=Rect(100, 100, 20, 20),
            confirm_button=Rect(130, 130, 20, 20),
            can_confirm=False,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.BLESSING_SETUP, 0.95, setup))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, setup.slots[0].target)
        self.assertIn("open blessing slot 1", action.reason)

    def test_blessing_setup_never_uses_auto_equip_when_slots_are_empty(self) -> None:
        setup = BlessingSetup(
            slots=[
                BlessingSlot(1, False, Rect(10, 10, 20, 20)),
                BlessingSlot(2, False, Rect(40, 40, 20, 20)),
            ],
            auto_equip_button=Rect(100, 100, 20, 20),
            confirm_button=Rect(130, 130, 20, 20),
            can_confirm=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.BLESSING_SETUP, 0.95, setup))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, setup.slots[0].target)
        self.assertNotEqual(action.target, setup.auto_equip_button)

    def test_blessing_setup_confirms_after_all_slots_are_filled(self) -> None:
        setup = BlessingSetup(
            slots=[
                BlessingSlot(1, True, Rect(10, 10, 20, 20)),
                BlessingSlot(2, True, Rect(40, 40, 20, 20)),
            ],
            auto_equip_button=Rect(100, 100, 20, 20),
            confirm_button=Rect(130, 130, 20, 20),
            can_confirm=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.BLESSING_SETUP, 0.95, setup))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, setup.confirm_button)

    def test_power_profile_picks_highest_power_blessing(self) -> None:
        choice = BlessingChoice(
            options=[
                BlessingOption("power_30", "power", 30, Rect(10, 10, 20, 20)),
                BlessingOption("power_50", "power", 50, Rect(40, 40, 20, 20)),
                BlessingOption("stamina_50", "stamina", 50, Rect(70, 70, 20, 20)),
            ]
        )

        action = TrainerPolicy().decide(
            GameState(build_profile="power_focus"),
            Observation(Screen.BLESSING_CHOICE, 0.95, choice),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.options[1].target)
        self.assertIn("power", action.reason)
        self.assertIn("50", action.reason)

    def test_blessing_tie_break_prefers_sub_blessing(self) -> None:
        choice = BlessingChoice(
            options=[
                BlessingOption("power_50_plain", "power", 50, Rect(10, 10, 20, 20)),
                BlessingOption("power_50_with_sub", "power", 50, Rect(40, 40, 20, 20), 1, ("attack_sense",)),
            ]
        )

        action = TrainerPolicy().decide(
            GameState(build_profile="power_focus"),
            Observation(Screen.BLESSING_CHOICE, 0.95, choice),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.options[1].target)
        self.assertIn("sub_blessings=1", action.reason)

    def test_blessing_tie_break_prefers_earlier_card_when_sub_blessings_are_unknown(self) -> None:
        choice = BlessingChoice(
            options=[
                BlessingOption("power_35_01", "power", 35, Rect(552, 270, 190, 210)),
                BlessingOption("power_35_02", "power", 35, Rect(802, 270, 190, 210)),
            ]
        )

        action = TrainerPolicy().decide(
            GameState(build_profile="power_focus"),
            Observation(Screen.BLESSING_CHOICE, 0.95, choice),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.options[0].target)

    def test_stamina_tank_profile_picks_stamina_blessing(self) -> None:
        choice = BlessingChoice(
            options=[
                BlessingOption("power_50", "power", 50, Rect(10, 10, 20, 20)),
                BlessingOption("stamina_45", "stamina", 45, Rect(40, 40, 20, 20)),
            ]
        )

        action = TrainerPolicy().decide(
            GameState(build_profile="stamina_tank"),
            Observation(Screen.BLESSING_CHOICE, 0.95, choice),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.options[1].target)
        self.assertIn("stamina", action.reason)

    def test_journey_start_ignores_arcana_and_clicks_start(self) -> None:
        journey = JourneyStart(
            start_button=Rect(1542, 1078, 430, 60),
            auto_journey_button=Rect(1300, 1078, 232, 60),
            arcana_slots=[Rect(1124, 392, 130, 292)],
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.JOURNEY_START, 0.95, journey))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, journey.start_button)
        self.assertIn("arcana is fixed", action.reason)

    def test_confirm_dialog_clicks_confirm_button(self) -> None:
        dialog = ConfirmDialog(
            title="entry_confirm",
            message="start_journey",
            confirm_button=Rect(1033, 753, 286, 60),
            cancel_button=Rect(730, 753, 286, 60),
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.CONFIRM_DIALOG, 0.95, dialog))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, dialog.confirm_button)
        self.assertIn("entry_confirm", action.reason)

    def test_event_fast_forward_selects_all_events_first(self) -> None:
        setting = EventFastForwardSetting(
            no_fast_forward_option=Rect(433, 389, 394, 306),
            watched_only_option=Rect(835, 389, 380, 300),
            all_events_option=Rect(1228, 389, 380, 300),
            confirm_button=Rect(882, 805, 286, 60),
            selected_mode="no_fast_forward",
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.EVENT_FAST_FORWARD_SETTING, 0.95, setting))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, setting.all_events_option)
        self.assertIn("select fast-forward all events", action.reason)

    def test_event_fast_forward_confirms_after_all_events_selected(self) -> None:
        setting = EventFastForwardSetting(
            no_fast_forward_option=Rect(433, 389, 394, 306),
            watched_only_option=Rect(835, 389, 380, 300),
            all_events_option=Rect(1228, 389, 380, 300),
            confirm_button=Rect(882, 805, 286, 60),
            selected_mode="all_events",
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.EVENT_FAST_FORWARD_SETTING, 0.95, setting))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, setting.confirm_button)
        self.assertIn("confirm fast-forward all events", action.reason)

    def test_dialogue_intro_uses_intro_skip_button(self) -> None:
        dialogue = DialogueScene(skip_button=Rect(1905, 40, 105, 55), variant="intro_story")

        action = TrainerPolicy().decide(GameState(), Observation(Screen.DIALOGUE, 0.95, dialogue))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, dialogue.skip_button)
        self.assertIn("intro_story", action.reason)

    def test_dialogue_journey_hud_uses_changed_skip_button(self) -> None:
        dialogue = DialogueScene(skip_button=Rect(1484, 43, 62, 52), variant="journey_hud")

        action = TrainerPolicy().decide(GameState(), Observation(Screen.DIALOGUE, 0.95, dialogue))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, dialogue.skip_button)
        self.assertIn("journey_hud", action.reason)

    def test_initial_relic_choice_uses_fixed_cuckoo_clock(self) -> None:
        choice = RelicChoice(
            options=[
                RelicOption("soft_toy_friend", 12, Rect(390, 263, 384, 604)),
                RelicOption("annoying_cuckoo_clock", 12, Rect(832, 263, 384, 604)),
                RelicOption("balanced_scale", 12, Rect(1275, 263, 384, 604)),
            ],
            confirm_button=Rect(863, 927, 322, 66),
            fixed_name="annoying_cuckoo_clock",
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.RELIC_CHOICE, 0.95, choice))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.options[1].target)
        self.assertIn("fixed relic", action.reason)

    def test_relic_choice_without_fixed_name_uses_highest_score(self) -> None:
        choice = RelicChoice(
            options=[
                RelicOption("low", 20, Rect(10, 10, 20, 20)),
                RelicOption("high", 80, Rect(40, 40, 20, 20)),
            ],
            confirm_button=Rect(100, 100, 20, 20),
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.RELIC_CHOICE, 0.95, choice))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.options[1].target)
        self.assertIn("highest relic score", action.reason)

    def test_selected_relic_choice_clicks_confirm(self) -> None:
        choice = RelicChoice(
            options=[RelicOption("annoying_cuckoo_clock", 12, Rect(832, 263, 384, 604))],
            confirm_button=Rect(863, 927, 322, 66),
            selected_name="annoying_cuckoo_clock",
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.RELIC_CHOICE, 0.95, choice))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.confirm_button)
        self.assertIn("confirm selected relic", action.reason)

    def test_event_choice_prefers_coin_cost_over_fatigue_cost(self) -> None:
        options = [
            EventOption("\u4ed8\u94b1\u8d2d\u4e70 50", Rect(10, 10, 20, 20)),
            EventOption("\u5bfb\u627e\u5f31\u70b9\u653b\u63a0", Rect(40, 40, 20, 20)),
            EventOption("\u7528\u529b\u91cf\u62d4\u51fa\u6765 \u75b2\u52b3\u503c 70", Rect(70, 70, 20, 20)),
            EventOption("\u76f4\u63a5\u8d70\u8fc7", Rect(100, 100, 20, 20)),
        ]

        action = TrainerPolicy().decide(GameState(), Observation(Screen.EVENT_CHOICE, 0.95, options))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, options[0].target)
        self.assertIn("spend coins", action.reason)

    def test_commission_select_first_click_selects_option(self) -> None:
        opt = CommissionOption("short_patrol", "C", True, Rect(1690, 330, 810, 120))
        accept = Rect(1740, 1285, 755, 85)
        choice = CommissionChoice(options=[opt], accept_button=accept)

        action = TrainerPolicy().decide(
            GameState(current_rank="C"),
            Observation(Screen.COMMISSION_SELECT, 0.95, choice),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, opt.target)
        self.assertIn("select commission", action.reason)

    def test_commission_select_second_click_accepts(self) -> None:
        opt = CommissionOption("short_patrol", "C", True, Rect(1690, 330, 810, 120))
        accept = Rect(1740, 1285, 755, 85)
        choice = CommissionChoice(options=[opt], accept_button=accept)

        policy = TrainerPolicy()
        state = GameState(current_rank="C")
        obs = Observation(Screen.COMMISSION_SELECT, 0.95, choice)

        # First iteration \u2014 selects option
        policy.decide(state, obs)
        # Second iteration \u2014 clicks accept
        action = policy.decide(state, obs)

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, accept)
        self.assertIn("accept commission", action.reason)

    def test_commission_select_no_accept_button_stays_on_select(self) -> None:
        opt = CommissionOption("short_patrol", "C", True, Rect(1690, 330, 810, 120))
        choice = CommissionChoice(options=[opt], accept_button=None)

        policy = TrainerPolicy()
        state = GameState(current_rank="C")
        obs = Observation(Screen.COMMISSION_SELECT, 0.95, choice)

        policy.decide(state, obs)
        action = policy.decide(state, obs)

        self.assertEqual(action.target, opt.target)
        self.assertIn("select commission", action.reason)

    def test_commission_select_accepts_lowest_tier_without_red_text(self) -> None:
        # The hub red banner is the gate; on the select screen accept the lowest
        # tier (first entry), which is always within the character's rank.
        low = CommissionOption("slime_low", "低阶委托", False, Rect(2050, 465, 380, 110))
        mid = CommissionOption("slime_mid", "中阶委托", False, Rect(2050, 640, 380, 110))
        choice = CommissionChoice(options=[low, mid], accept_button=Rect(1880, 1255, 600, 100))

        policy = TrainerPolicy()
        obs = Observation(Screen.COMMISSION_SELECT, 0.95, choice)
        select = policy.decide(GameState(), obs)
        accept = policy.decide(GameState(), obs)

        self.assertEqual(select.target, low.target)
        self.assertIn("select commission", select.reason)
        self.assertEqual(accept.target, choice.accept_button)
        self.assertIn("accept commission", accept.reason)

    def test_commission_select_exits_when_no_options(self) -> None:
        # Empty list → leave via the back arrow instead of getting stuck.
        back = Rect(90, 62, 55, 64)
        choice = CommissionChoice(options=[], accept_button=Rect(1880, 1255, 600, 100), back_button=back)

        action = TrainerPolicy().decide(
            GameState(),
            Observation(Screen.COMMISSION_SELECT, 0.95, choice),
        )

        self.assertEqual(action.target, back)
        self.assertIn("exit", action.reason)

    def test_event_choice_avoids_fatigue_cost_when_no_coin_option_exists(self) -> None:
        options = [
            EventOption("\u7528\u529b\u91cf\u62d4\u51fa\u6765 \u75b2\u52b3\u503c 70", Rect(10, 10, 20, 20)),
            EventOption("\u76f4\u63a5\u8d70\u8fc7", Rect(40, 40, 20, 20)),
        ]

        action = TrainerPolicy().decide(GameState(), Observation(Screen.EVENT_CHOICE, 0.95, options))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, options[1].target)
        self.assertNotEqual(action.target, options[0].target)

    def test_event_choice_avoids_ocr_variant_of_force_pull(self) -> None:
        options = [
            EventOption("\u7528\u529b\u91cf\u6273\u51fa\u6765", Rect(10, 10, 20, 20)),
            EventOption("\u76f4\u63a5\u8d70\u8fc7", Rect(40, 40, 20, 20)),
        ]

        action = TrainerPolicy().decide(GameState(), Observation(Screen.EVENT_CHOICE, 0.95, options))

        self.assertEqual(action.target, options[1].target)


if __name__ == "__main__":
    unittest.main()
