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
    RestSubmenu,
    Screen,
    ShopItem,
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

    def test_reward_screen_clicks_continue_prompt_not_dead_centre(self) -> None:
        policy = TrainerPolicy()

        action = policy.decide(GameState(), Observation(Screen.REWARD, 1.0))

        self.assertEqual(action.kind, "click")
        # The 点击以继续 prompt (bottom-centre), NOT the dead centre relic card.
        self.assertEqual(action.target, policy.config.reward_continue_button)

    def test_dialogue_skip_is_a_burst_to_advance_fast(self) -> None:
        action = TrainerPolicy().decide_dialogue(DialogueScene(skip_button=Rect(1855, 54, 78, 65)))

        self.assertEqual(action.kind, "click")
        self.assertGreater(action.repeat, 1)

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

    def test_character_select_picks_variant_form_by_desired_variant(self) -> None:
        # 游戏更新后同名角色有2形态(普通 / ANOTHER), 区别在每行职业图标下方的形态文字。
        # desired_variant=ANOTHER 时必须选 ANOTHER 那个卡蜜, 不能选普通的。
        base = CharacterOption("卡蜜", None, None, None, False, Rect(2030, 250, 458, 122), variant="")
        another = CharacterOption("卡蜜", None, None, None, False, Rect(2030, 394, 458, 122), variant="ANOTHER")
        selection = CharacterSelect(
            options=[base, another],
            confirm_button=Rect(2038, 1305, 448, 75),
            selected_name=None,
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="卡蜜", desired_variant="ANOTHER"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.target, another.target)

    def test_character_select_picks_base_form_when_no_variant_desired(self) -> None:
        # desired_variant 为空(默认) → 选普通形态(无形态文字)的那个, 不选 ANOTHER。
        base = CharacterOption("卡蜜", None, None, None, False, Rect(2030, 250, 458, 122), variant="")
        another = CharacterOption("卡蜜", None, None, None, False, Rect(2030, 394, 458, 122), variant="ANOTHER")
        selection = CharacterSelect(
            options=[another, base],  # ANOTHER 在前, 仍应选 base
            confirm_button=Rect(2038, 1305, 448, 75),
            selected_name=None,
        )

        action = TrainerPolicy().decide(
            GameState(desired_character="卡蜜"),
            Observation(Screen.CHARACTER_SELECT, 0.95, selection),
        )

        self.assertEqual(action.target, base.target)

    def test_blessing_choice_two_step_confirm_for_same_value(self) -> None:
        # 多个同值(35)体力祝福: 第1帧选靠上第一个(选中), 第2帧两步防抖确认 —— 不能依赖
        # selected_name(同值卡 OCR 分不清, 会永不确认→死循环)。
        policy = TrainerPolicy()
        st = GameState(build_profile="stamina_tank")
        confirm = Rect(300, 300, 80, 40)
        top = BlessingOption("s35_top", "stamina", 35, Rect(10, 10, 20, 20))
        bot = BlessingOption("s35_bot", "stamina", 35, Rect(10, 300, 20, 20))
        choice = BlessingChoice([top, bot], confirm_button=confirm)
        a1 = policy.decide(st, Observation(Screen.BLESSING_CHOICE, 1.0, choice))
        self.assertEqual(a1.kind, "click")
        self.assertEqual(a1.target, top.target)  # 选靠上第一个
        a2 = policy.decide(st, Observation(Screen.BLESSING_CHOICE, 1.0, choice))
        self.assertEqual(a2.target, confirm)  # 第2帧确认(防抖)

    def test_blessing_choice_confirms_despite_candidate_flicker(self) -> None:
        # 候选数帧间抖动(同值卡时有时无)不应死循环: 选中后下帧即使候选变了也确认。
        policy = TrainerPolicy()
        st = GameState(build_profile="stamina_tank")
        confirm = Rect(300, 300, 80, 40)
        top = BlessingOption("s35_top", "stamina", 35, Rect(10, 10, 20, 20))
        bot = BlessingOption("s35_bot", "stamina", 35, Rect(10, 300, 20, 20))
        full = BlessingChoice([top, bot], confirm_button=confirm)
        flick = BlessingChoice([bot], confirm_button=confirm)  # top 抖动消失
        policy.decide(st, Observation(Screen.BLESSING_CHOICE, 1.0, full))  # 选 top, 记 pending
        a2 = policy.decide(st, Observation(Screen.BLESSING_CHOICE, 1.0, flick))
        self.assertEqual(a2.target, confirm)  # 候选抖动, 仍两步确认

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

    def test_character_select_two_step_confirm_when_name_unverifiable(self) -> None:
        # bbox path: clicking her row selects her, but the left-panel name OCR
        # often can't verify it (selected_name stays a placeholder). After clicking
        # her row once, the next sighting must click 选择 to confirm — not re-click.
        policy = TrainerPolicy()
        state = GameState(desired_character="罗莎莉亚")
        row = Rect(2120, 700, 180, 56)
        confirm = Rect(2038, 1305, 448, 75)
        sel = CharacterSelect(
            options=[CharacterOption("罗莎莉亚", None, None, None, False, row)],
            confirm_button=confirm,
            selected_name="selected_character",  # unreadable -> never flags selected
            can_scroll=True,
        )

        first = policy.decide_character_select(sel, state)
        self.assertEqual(first.kind, "click")
        self.assertEqual(first.target, row)
        self.assertIn("select desired character", first.reason)

        second = policy.decide_character_select(sel, state)
        self.assertEqual(second.kind, "click")
        self.assertEqual(second.target, confirm)
        self.assertIn("confirm desired character", second.reason)

    def _char_sel(self, names: list[str]) -> CharacterSelect:
        opts = [
            CharacterOption(n, None, None, None, False, Rect(2030, 250 + i * 144, 458, 122))
            for i, n in enumerate(names)
        ]
        return CharacterSelect(options=opts, confirm_button=Rect(2038, 1305, 448, 75), selected_name=None, can_scroll=True)

    def test_character_select_reverses_scroll_when_list_end_reached(self) -> None:
        # Regression for the live-run infinite-scroll bug: the target may be ABOVE
        # the starting position. Scroll down first; when the view stops changing
        # (list end), reverse to up so above-start entries get searched too.
        policy = TrainerPolicy()
        state = GameState(desired_character="罗莎莉亚")
        a = self._char_sel(["a", "b", "c", "d", "e", "f", "g"])
        b = self._char_sel(["d", "e", "f", "g", "h", "i", "j"])

        first = policy.decide_character_select(a, state)
        self.assertEqual(first.kind, "scroll")
        self.assertLess(first.scroll_clicks, 0)  # down
        policy.decide_character_select(b, state)  # view changed → keep going down
        reversed_action = policy.decide_character_select(b, state)  # unchanged → reverse to up
        self.assertGreater(reversed_action.scroll_clicks, 0)  # up
        # No oscillation: stays going up while the view keeps not changing.
        again = policy.decide_character_select(b, state)
        self.assertGreater(again.scroll_clicks, 0)

    def test_character_select_pauses_after_scroll_cap(self) -> None:
        # Bounded search: after a full bidirectional scan it stops (pauses) instead
        # of scrolling forever.
        policy = TrainerPolicy()
        state = GameState(desired_character="罗莎莉亚")
        actions = [
            policy.decide_character_select(self._char_sel([f"x{i}", f"y{i}", "c", "d", "e", "f", "g"]), state)
            for i in range(34)
        ]
        self.assertTrue(all(a.kind == "scroll" for a in actions[:30]))
        self.assertTrue(all(a.kind == "pause" for a in actions[30:]))

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

    def _rest(self, coins: int, *, confirm=True) -> RestSubmenu:
        return RestSubmenu(
            coins=coins,
            has_meditation_room=True,
            meditation_room=Rect(2000, 800, 460, 110),
            rough_sleep=Rect(2000, 498, 460, 110),
            lodging=Rect(2000, 648, 460, 110),
            confirm_button=Rect(2050, 1255, 420, 95) if confirm else None,
        )

    def test_rest_picks_meditation_when_coins_high(self) -> None:
        rest = self._rest(70)
        action = TrainerPolicy().decide_rest(rest)
        self.assertEqual(action.target, rest.meditation_room)
        self.assertIn("meditation", action.reason)

    def test_rest_picks_lodging_when_coins_mid(self) -> None:
        # 30 <= coins < 60 → 住处 (lodging), per the user's rule (not free 露宿).
        rest = self._rest(48)
        action = TrainerPolicy().decide_rest(rest)
        self.assertEqual(action.target, rest.lodging)
        self.assertIn("lodging", action.reason)

    def test_rest_picks_rough_sleep_when_broke(self) -> None:
        rest = self._rest(10)
        action = TrainerPolicy().decide_rest(rest)
        self.assertEqual(action.target, rest.rough_sleep)
        self.assertIn("rough_sleep", action.reason)

    def test_rest_two_step_select_then_confirm(self) -> None:
        policy = TrainerPolicy()
        rest = self._rest(48)
        first = policy.decide_rest(rest)
        second = policy.decide_rest(rest)
        self.assertEqual(first.target, rest.lodging)
        self.assertIn("select", first.reason)
        self.assertEqual(second.target, rest.confirm_button)
        self.assertIn("confirm", second.reason)

    def test_rest_single_click_when_no_confirm_button(self) -> None:
        rest = self._rest(48, confirm=False)
        action = TrainerPolicy().decide_rest(rest)
        self.assertEqual(action.target, rest.lodging)

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

    def test_training_hub_skips_skill_learning_midrun(self) -> None:
        # 技能留到跑马完成后再学(前期学技能不影响跑马);大厅即使可学技能也直接训练。
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            commission_button=Rect(40, 40, 20, 20),
            rest_button=Rect(70, 70, 20, 20),
            skill_button=Rect(100, 100, 20, 20),
            can_learn_skill=True,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, hub.training_button)
        self.assertNotIn("skill", action.reason)

    def test_training_hub_ignores_potential_points_midrun(self) -> None:
        # 潜质点够也不中途学技能,直接训练。
        hub = TrainingHubStatus(
            training_button=Rect(10, 10, 20, 20),
            skill_button=Rect(100, 100, 20, 20),
            potential_points=120,
        )

        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))

        self.assertEqual(action.target, hub.training_button)

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

    def test_shop_buys_stamina_recovery_by_effect(self) -> None:
        # 按效果买(名字与效果无关): 含"回复体力"→买。
        items = [ShopItem("炸蔬菜", 24, Rect(10, 10, 20, 20), effect="首次战斗开始时回复体力10")]
        action = TrainerPolicy().decide_shop(items)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, items[0].target)

    def test_shop_buys_potential_refund_by_effect(self) -> None:
        # 手持风扇效果是"伤害+1%"但"潜质点数8退还"→买(白嫖潜质点)。
        items = [ShopItem("手持随身风扇", 40, Rect(10, 10, 20, 20), effect="每回合伤害增加1%。潜质点数 8 退还")]
        action = TrainerPolicy().decide_shop(items)
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, items[0].target)

    def test_shop_skips_items_without_wanted_effect(self) -> None:
        # 效果不含想要关键词(纯攻击护符,非潜质退还/回体力)→ 不买(退出)。
        items = [ShopItem("某护符", 30, Rect(10, 10, 20, 20), effect="攻击力增加5%")]
        action = TrainerPolicy().decide_shop(items)
        self.assertEqual(action.kind, "skip")

    def test_dday_hub_visits_trading_before_battle(self) -> None:
        # D-DAY 评鉴战大厅(有评鉴战+交易按钮): 先去交易(打过评鉴战交易就消失)。
        hub = TrainingHubStatus(rating_battle_button=Rect(10, 10, 20, 20), trading_button=Rect(40, 40, 20, 20))
        action = TrainerPolicy().decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))
        self.assertEqual(action.target, hub.trading_button)

    def test_dday_hub_goes_battle_after_trading(self) -> None:
        hub = TrainingHubStatus(rating_battle_button=Rect(10, 10, 20, 20), trading_button=Rect(40, 40, 20, 20))
        policy = TrainerPolicy()
        policy._dday_trading_done = True  # 已逛过交易
        action = policy.decide(GameState(), Observation(Screen.TRAINING_HUB, 0.95, hub))
        self.assertEqual(action.target, hub.rating_battle_button)

    def test_shop_exit_marks_dday_trading_done(self) -> None:
        # 交易逛完(没想买的→退出)后标记已逛, 这样回 D-DAY 大厅就去评鉴战。
        policy = TrainerPolicy()
        policy.decide_shop([ShopItem("x", 30, Rect(10, 10, 20, 20), effect="攻击力+5")])
        self.assertTrue(policy._dday_trading_done)

    def test_normal_hub_resets_dday_trading_done(self) -> None:
        # 评鉴战日逛完交易后(_dday_trading_done=True), 回到普通大厅(无评鉴战按钮)应清掉
        # 该一次性标记, 这样下一个评鉴战日还会先去交易。
        policy = TrainerPolicy()
        policy._dday_trading_done = True
        hub = TrainingHubStatus(training_button=Rect(10, 10, 20, 20))  # 普通大厅, 无 rating_battle_button
        policy.decide(GameState(), Observation(Screen.TRAINING_HUB, 0.9, hub))
        self.assertFalse(policy._dday_trading_done)

    def test_skill_select_uses_build_profile_keywords(self) -> None:
        options = [
            SkillOption("生命感知", cost=100, target=Rect(10, 10, 20, 20)),
            SkillOption("攻击感知", cost=90, target=Rect(40, 40, 20, 20)),
        ]

        # decide_skill 终局仍按 build 关键词选(直接测它);大厅/界面前期不再进技能学习。
        action = TrainerPolicy().decide_skill(options, GameState(build_profile="power_focus"))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, options[1].target)
        self.assertIn("攻击感知", action.reason)

    def test_skill_select_avoids_learned_options(self) -> None:
        options = [
            SkillOption("已习得 攻击感知", cost=90, target=Rect(10, 10, 20, 20)),
            SkillOption("未习得 生命感知", cost=100, target=Rect(40, 40, 20, 20)),
        ]

        action = TrainerPolicy().decide_skill(options, GameState(build_profile="power_focus"))

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, options[1].target)

    def test_skill_select_exits_midrun_via_close_button(self) -> None:
        # 前期进了技能界面 → 点右上角 ✕ 退出(技能留到跑马完成后),不在前期学技能。
        options = [SkillOption("攻击感知", cost=90, target=Rect(40, 40, 20, 20))]
        policy = TrainerPolicy()
        action = policy.decide(
            GameState(build_profile="power_focus"),
            Observation(Screen.SKILL_SELECT, 0.95, options),
        )
        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, policy.config.skill_select_close_button)

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

    def test_blessing_tie_break_ignores_sub_blessing_picks_topmost(self) -> None:
        # sub-blessing 数 OCR 不可靠(实机在帧间 0/2 跳, 还导致死循环)→ 不按它 tiebreak;
        # 同值祝福价值相同, 按位置选靠上第一个(稳定)即可。
        choice = BlessingChoice(
            options=[
                BlessingOption("power_50_top", "power", 50, Rect(10, 10, 20, 20)),
                BlessingOption("power_50_with_sub", "power", 50, Rect(40, 40, 20, 20), 1, ("attack_sense",)),
            ]
        )

        action = TrainerPolicy().decide(
            GameState(build_profile="power_focus"),
            Observation(Screen.BLESSING_CHOICE, 0.95, choice),
        )

        self.assertEqual(action.kind, "click")
        self.assertEqual(action.target, choice.options[0].target)  # 靠上(y=10), 忽略 sub

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

    def test_relic_choice_two_step_confirms_instead_of_oscillating(self) -> None:
        # Regression: a normal relic choice never sets selected_name, so the old
        # code re-ran decide_relic every frame and the pick flipped between
        # near-scored cards (OCR noise) — endless back-and-forth, never confirming.
        # Now it locks the first pick and confirms next frame.
        policy = TrainerPolicy()
        confirm = Rect(100, 100, 20, 20)
        low, high = Rect(10, 10, 20, 20), Rect(40, 40, 20, 20)

        first = policy.decide(
            GameState(),
            Observation(
                Screen.RELIC_CHOICE, 0.95,
                RelicChoice([RelicOption("low", 20, low), RelicOption("high", 80, high)], confirm_button=confirm),
            ),
        )
        self.assertEqual(first.target, high)  # picks the highest score first

        # Next frame the scores flip (simulating OCR noise on the highlighted card):
        # it must CONFIRM the earlier pick, not re-pick the now-"better" card.
        second = policy.decide(
            GameState(),
            Observation(
                Screen.RELIC_CHOICE, 0.95,
                RelicChoice([RelicOption("low", 80, low), RelicOption("high", 20, high)], confirm_button=confirm),
            ),
        )
        self.assertEqual(second.target, confirm)
        self.assertIn("confirm", second.reason)

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


class RoundStrategyTrainingTests(unittest.TestCase):
    """前12回合 力量/体力 加权打分 — round-aware early-game training weighting.

    Early rounds favour 力量(power)/生命(stamina): inside the early window each
    gets a score weight added (still compared against the others, not forced).
    """

    def test_early_round_adds_weight_to_power_and_stamina(self) -> None:
        policy = TrainerPolicy()
        power = TrainingChoice("power", 10, "none", 0, Rect(0, 0, 10, 10))
        stamina = TrainingChoice("stamina", 10, "none", 0, Rect(0, 0, 10, 10))
        for choice in (power, stamina):
            base = policy.training_score(choice, GameState(current_round=None))
            early = policy.training_score(choice, GameState(current_round=3))
            self.assertEqual(early - base, 15, choice.name)

    def test_round_12_boundary_is_inclusive(self) -> None:
        policy = TrainerPolicy()
        power = TrainingChoice("power", 10, "none", 0, Rect(0, 0, 10, 10))
        base = policy.training_score(power, GameState(current_round=None))
        self.assertEqual(policy.training_score(power, GameState(current_round=12)) - base, 15)

    def test_no_weight_after_early_window(self) -> None:
        policy = TrainerPolicy()
        power = TrainingChoice("power", 10, "none", 0, Rect(0, 0, 10, 10))
        base = policy.training_score(power, GameState(current_round=None))
        self.assertEqual(policy.training_score(power, GameState(current_round=13)), base)

    def test_non_target_stat_gets_no_early_weight(self) -> None:
        policy = TrainerPolicy()
        guts = TrainingChoice("guts", 10, "none", 0, Rect(0, 0, 10, 10))
        base = policy.training_score(guts, GameState(current_round=None))
        self.assertEqual(policy.training_score(guts, GameState(current_round=3)), base)

    def test_early_weight_does_not_override_fail_veto(self) -> None:
        # A too-risky card stays vetoed (-inf) even inside the early window — the
        # weight is added after the fail-rate guard, never rescues an over-failed card.
        policy = TrainerPolicy()
        risky = TrainingChoice("power", 10, "none", 99, Rect(0, 0, 10, 10))
        self.assertEqual(policy.training_score(risky, GameState(current_round=1)), float("-inf"))

    def test_early_weight_can_flip_the_training_choice(self) -> None:
        # balanced build: wisdom's higher base (30) beats power (20) normally, but in
        # the early window power's +15 weight (35) overtakes it.
        confirm = Rect(2080, 1252, 400, 95)
        power = TrainingChoice("power", 20, "none", 0, Rect(1750, 338, 650, 112), confirm_button=confirm)
        wisdom = TrainingChoice("wisdom", 30, "none", 0, Rect(1750, 487, 650, 112), confirm_button=confirm)
        policy = TrainerPolicy()

        late = policy.decide_training([power, wisdom], GameState(current_round=None))
        early = policy.decide_training([power, wisdom], GameState(current_round=3))

        self.assertEqual(late.target, wisdom.target)
        self.assertEqual(early.target, power.target)
        self.assertIn("power", early.reason)

    def test_early_round_amplifies_ring_bonus_2_5x(self) -> None:
        # guts isolates the ring effect (no power/stamina early stat weight).
        policy = TrainerPolicy()
        rainbow = TrainingChoice("guts", 0, "rainbow", 0, Rect(0, 0, 10, 10))
        self.assertEqual(policy.training_score(rainbow, GameState(current_round=None)), 40)
        self.assertEqual(policy.training_score(rainbow, GameState(current_round=3)), 100)

    def test_ring_amplification_off_after_early_window(self) -> None:
        policy = TrainerPolicy()
        rainbow = TrainingChoice("guts", 0, "rainbow", 0, Rect(0, 0, 10, 10))
        self.assertEqual(policy.training_score(rainbow, GameState(current_round=13)), 40)

    def test_ring_amplification_boundary_round_12_inclusive(self) -> None:
        policy = TrainerPolicy()
        gold = TrainingChoice("guts", 0, "gold", 0, Rect(0, 0, 10, 10))
        self.assertEqual(policy.training_score(gold, GameState(current_round=12)), 62.5)

    def test_no_ring_means_no_amplification(self) -> None:
        policy = TrainerPolicy()
        plain = TrainingChoice("guts", 0, "none", 0, Rect(0, 0, 10, 10))
        self.assertEqual(policy.training_score(plain, GameState(current_round=3)), 0)

    def test_ring_amplification_stacks_with_early_stat_weight(self) -> None:
        # power gets BOTH: ring 40*2.5=100 AND the early stat weight +15.
        policy = TrainerPolicy()
        power_rainbow = TrainingChoice("power", 0, "rainbow", 0, Rect(0, 0, 10, 10))
        self.assertEqual(policy.training_score(power_rainbow, GameState(current_round=3)), 115)


class RelicComboTests(unittest.TestCase):
    """组合圣遗物(队员全体)按部位属性 + build 优先级选; 普通(伙伴专用)按徽章分."""

    _CONFIRM = Rect(1080, 1158, 400, 82)

    def _combo(self, *attr_x):
        opts = [
            RelicOption(f"relic_{a}", 4, Rect(x, 330, 480, 750), attribute=a, is_team=True)
            for a, x in attr_x
        ]
        return RelicChoice(options=opts, confirm_button=self._CONFIRM)

    def test_power_picks_attack_glove(self) -> None:
        ch = self._combo(("attack", 485), ("hp", 1040), ("crit_dmg", 1593))
        action = TrainerPolicy().decide_relic_choice(ch, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, ch.options[0].target)  # 手套(攻击力)最优

    def test_power_falls_to_crit_dmg_when_no_attack_or_critrate(self) -> None:
        # 铠甲hp/眼镜hit/项链crit_dmg → 攻击/暴击率都没 → 取暴伤(项链)= 实机那一屏的正确解
        ch = self._combo(("hp", 485), ("hit", 1040), ("crit_dmg", 1593))
        action = TrainerPolicy().decide_relic_choice(ch, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, ch.options[2].target)

    def test_power_random_first_when_none_in_priority(self) -> None:
        # 优先级里3个属性都没出现 → 随便选(取第一张)
        ch = self._combo(("hp", 485), ("defense", 1040), ("resist", 1593))
        action = TrainerPolicy().decide_relic_choice(ch, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, ch.options[0].target)

    def test_stamina_picks_hp_armor(self) -> None:
        ch = self._combo(("hp", 485), ("hit", 1040), ("crit_dmg", 1593))
        action = TrainerPolicy().decide_relic_choice(ch, GameState(build_profile="stamina_tank"))
        self.assertEqual(action.target, ch.options[0].target)  # 铠甲(生命)最优

    def test_normal_relic_picks_highest_score(self) -> None:
        ch = RelicChoice(
            options=[
                RelicOption("a", 8, Rect(485, 330, 480, 750), is_team=False),
                RelicOption("b", 12, Rect(1040, 330, 480, 750), is_team=False),
            ],
            confirm_button=self._CONFIRM,
        )
        action = TrainerPolicy().decide_relic_choice(ch, GameState(build_profile="power_focus"))
        self.assertEqual(action.target, ch.options[1].target)  # 徽章分12 最高


if __name__ == "__main__":
    unittest.main()
