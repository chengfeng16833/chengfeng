"""Screen handler registry.

Single source of truth mapping each Screen to its handler. The classifier,
policy, and live loop dispatch through HANDLERS instead of hardcoded if/elif
chains, so adding a screen means adding one entry here (plus region JSON).

During this (delegation) phase, handlers forward to the existing, already-tested
``parse_X`` / ``decide_X`` / ``_has_X_signature`` functions — behaviour is 1:1
with the pre-refactor code. The decide_fns below are verbatim copies of the
branches that used to live in TrainerPolicy.decide; they take the policy instance
so they can use its config and instance state unchanged.

Physical relocation of each screen's logic into its own file is deferred — see
REFACTOR.md "待物理搬迁".
"""

from __future__ import annotations

from starsavior_trainer.classifier import (
    _has_commission_select_signature,
    _has_dialogue_signature,
    _has_event_choice_signature,
    _has_initial_signature,
    _has_post_training_signature,
    _has_rest_submenu_signature,
    _has_shop_signature,
    _has_training_hub_shop_signature,
    _has_training_select_signature,
)
from starsavior_trainer.models import (
    Action,
    BattleScene,
    BlessingChoice,
    BlessingSetup,
    CharacterSelect,
    CommissionChoice,
    ConfirmDialog,
    DialogueScene,
    EventFastForwardSetting,
    EventOption,
    JourneyStart,
    RelicChoice,
    RelicOption,
    RestSubmenu,
    Screen,
    ShopItem,
    SkillOption,
    TrainingChoice,
    TrainingHubStatus,
)
from starsavior_trainer.policy import _is_iterable_of
from starsavior_trainer.screen_reader import (
    PostTrainingResult,
    parse_battle,
    parse_blessing_choice,
    parse_blessing_setup,
    parse_character_select,
    parse_commission_select,
    parse_confirm_dialog,
    parse_dialogue_scene,
    parse_event_choice,
    parse_event_fast_forward_setting,
    parse_journey_start,
    parse_post_training,
    parse_region_move,
    parse_relic_choice,
    parse_rest_submenu,
    parse_shop,
    parse_skill_select,
    parse_training_direction,
    parse_training_hub,
    parse_training_select,
)
from starsavior_trainer.screens.base import DelegatingScreenHandler


# ---------------------------------------------------------------------------
# Decision functions — verbatim copies of the old TrainerPolicy.decide branches.
# Each takes (observation, state, policy) and must stay behaviourally identical.
# ---------------------------------------------------------------------------


def _decide_initial(obs, state, policy):
    return Action("click", policy.config.start_button, "initial screen, click start")


def _decide_character_select(obs, state, policy):
    if not isinstance(obs.payload, CharacterSelect):
        return Action("pause", None, "character select screen missing character observation")
    return policy.decide_character_select(obs.payload, state)


def _decide_blessing_setup(obs, state, policy):
    if not isinstance(obs.payload, BlessingSetup):
        return Action("pause", None, "blessing setup screen missing setup observation")
    return policy.decide_blessing_setup(obs.payload)


def _decide_blessing_choice(obs, state, policy):
    if not isinstance(obs.payload, BlessingChoice):
        return Action("pause", None, "blessing choice screen missing options")
    return policy.decide_blessing_choice(obs.payload, state)


def _decide_journey_start(obs, state, policy):
    if not isinstance(obs.payload, JourneyStart):
        return Action("pause", None, "journey start screen missing start button")
    return policy.decide_journey_start(obs.payload)


def _decide_confirm_dialog(obs, state, policy):
    if not isinstance(obs.payload, ConfirmDialog):
        return Action("pause", None, "confirm dialog missing button observation")
    return policy.decide_confirm_dialog(obs.payload)


def _decide_event_fast_forward_setting(obs, state, policy):
    if not isinstance(obs.payload, EventFastForwardSetting):
        return Action("pause", None, "event fast-forward setting missing option observation")
    return policy.decide_event_fast_forward_setting(obs.payload)


def _decide_dialogue(obs, state, policy):
    if isinstance(obs.payload, DialogueScene):
        return policy.decide_dialogue(obs.payload)
    return Action("click", policy.config.skip_button, "dialogue screen, click skip")


def _decide_training_hub(obs, state, policy):
    if isinstance(obs.payload, TrainingHubStatus):
        if obs.payload.has_commission_alert and obs.payload.commission_button is not None:
            return Action("click", obs.payload.commission_button, "training hub, commission alert")
        if obs.payload.has_shop_alert and obs.payload.shop_button is not None:
            return Action("click", obs.payload.shop_button, "training hub, shop alert")
        if obs.payload.skill_button is not None and (
            obs.payload.can_learn_skill
            or (
                obs.payload.potential_points is not None
                and obs.payload.potential_points >= policy.config.min_skill_points
            )
        ):
            return Action("click", obs.payload.skill_button, "training hub, open skill learning")
        if obs.payload.training_button is not None:
            return Action("click", obs.payload.training_button, "training hub, enter training")
    return Action("click", policy.config.start_button, "training hub, click training")


def _decide_training_select(obs, state, policy):
    if not _is_iterable_of(obs.payload, TrainingChoice):
        return Action("pause", None, "training screen missing training choices")
    return policy.decide_training(obs.payload, state)


def _decide_rest_submenu(obs, state, policy):
    if not isinstance(obs.payload, RestSubmenu):
        return Action("pause", None, "rest screen missing submenu observation")
    return policy.decide_rest(obs.payload)


def _decide_event_choice(obs, state, policy):
    if not _is_iterable_of(obs.payload, EventOption):
        return Action("pause", None, "event screen missing options")
    return policy.decide_event(obs.payload, state)


def _decide_relic_choice(obs, state, policy):
    if isinstance(obs.payload, RelicChoice):
        return policy.decide_relic_choice(obs.payload)
    if not _is_iterable_of(obs.payload, RelicOption):
        return Action("pause", None, "relic screen missing options")
    return policy.decide_relic(obs.payload)


def _decide_commission_select(obs, state, policy):
    if not isinstance(obs.payload, CommissionChoice):
        policy._pending_commission = None
        return Action("pause", None, "commission screen missing options")
    return policy.decide_commission(obs.payload, state)


def _decide_shop(obs, state, policy):
    if not _is_iterable_of(obs.payload, ShopItem):
        return Action("pause", None, "shop screen missing item list")
    return policy.decide_shop(obs.payload)


def _decide_battle(obs, state, policy):
    if isinstance(obs.payload, BattleScene):
        if obs.payload.confirm_active and obs.payload.confirm_button is not None:
            return Action("click", obs.payload.confirm_button, "battle, accept battle")
        return Action("click", obs.payload.skip_button, "battle, open battle entry")
    return Action("click", policy.config.skip_button, "battle, click default action")


def _decide_skill_select(obs, state, policy):
    if _is_iterable_of(obs.payload, SkillOption):
        return policy.decide_skill(obs.payload, state)
    return Action("pause", None, "skill select screen missing options")


def _decide_post_training(obs, state, policy):
    if isinstance(obs.payload, PostTrainingResult) and obs.payload.skip_button is not None:
        return Action("click", obs.payload.skip_button, "post-training, click skip")
    return Action("click", policy.config.skip_button, "post-training, click skip")


def _decide_region_move(obs, state, policy):
    return Action("click", policy.config.move_button, "region move screen, click move")


# ---------------------------------------------------------------------------
# Parse helper — EVENT_CHOICE tries the training-direction event first.
# ---------------------------------------------------------------------------


def _parse_event_choice_combined(region_texts, profile):
    direction = parse_training_direction(region_texts, profile)
    if direction is not None:
        return direction
    return parse_event_choice(region_texts, profile)


# ---------------------------------------------------------------------------
# Registry. anchor_fn + priority replicate the ordered _match_screen signature
# checks (lower priority = checked first). Screens without an anchor_fn rely on
# the classifier's fallback anchor-text scoring (unchanged).
# ---------------------------------------------------------------------------

HANDLERS: dict[Screen, DelegatingScreenHandler] = {
    Screen.INITIAL: DelegatingScreenHandler(
        Screen.INITIAL, _decide_initial, priority=1,
        anchor_fn=_has_initial_signature, anchor_confidence=1.0,
        parse_fn=None, ocr_prefixes=None,
    ),
    Screen.POST_TRAINING: DelegatingScreenHandler(
        Screen.POST_TRAINING, _decide_post_training, priority=2,
        anchor_fn=_has_post_training_signature, anchor_confidence=1.0,
        parse_fn=parse_post_training, ocr_prefixes=["post_training"],
    ),
    Screen.EVENT_CHOICE: DelegatingScreenHandler(
        Screen.EVENT_CHOICE, _decide_event_choice, priority=3,
        anchor_fn=_has_event_choice_signature, anchor_confidence=1.0,
        parse_fn=_parse_event_choice_combined, ocr_prefixes=["event_choice", "training_direction"],
    ),
    Screen.DIALOGUE: DelegatingScreenHandler(
        Screen.DIALOGUE, _decide_dialogue, priority=4,
        anchor_fn=_has_dialogue_signature, anchor_confidence=1.0,
        parse_fn=parse_dialogue_scene, ocr_prefixes=["dialogue"],
    ),
    Screen.REST_SUBMENU: DelegatingScreenHandler(
        Screen.REST_SUBMENU, _decide_rest_submenu, priority=5,
        anchor_fn=_has_rest_submenu_signature, anchor_confidence=1.0,
        parse_fn=parse_rest_submenu, ocr_prefixes=["rest_submenu"],
    ),
    Screen.COMMISSION_SELECT: DelegatingScreenHandler(
        Screen.COMMISSION_SELECT, _decide_commission_select, priority=6,
        anchor_fn=_has_commission_select_signature, anchor_confidence=1.0,
        parse_fn=parse_commission_select, parse_needs_image=True, ocr_prefixes=["commission_select"],
    ),
    Screen.SHOP: DelegatingScreenHandler(
        Screen.SHOP, _decide_shop, priority=7,
        anchor_fn=_has_shop_signature, anchor_confidence=1.0,
        parse_fn=parse_shop, parse_needs_image=True, ocr_prefixes=["shop_item"],
    ),
    Screen.TRAINING_HUB: DelegatingScreenHandler(
        Screen.TRAINING_HUB, _decide_training_hub, priority=8,
        anchor_fn=_has_training_hub_shop_signature, anchor_confidence=1.0,
        parse_fn=parse_training_hub, parse_needs_image=True, ocr_prefixes=["training_hub"],
    ),
    Screen.TRAINING_SELECT: DelegatingScreenHandler(
        Screen.TRAINING_SELECT, _decide_training_select, priority=9,
        anchor_fn=_has_training_select_signature, anchor_confidence=0.90,
        parse_fn=parse_training_select, parse_needs_image=True, ocr_prefixes=["training_select"],
    ),
    # Screens resolved by the classifier's fallback anchor-text scoring (no signature).
    Screen.CHARACTER_SELECT: DelegatingScreenHandler(
        Screen.CHARACTER_SELECT, _decide_character_select,
        parse_fn=parse_character_select, ocr_prefixes=["character"],
    ),
    Screen.BLESSING_SETUP: DelegatingScreenHandler(
        Screen.BLESSING_SETUP, _decide_blessing_setup,
        parse_fn=parse_blessing_setup, parse_needs_image=True, ocr_prefixes=["blessing"],
    ),
    Screen.BLESSING_CHOICE: DelegatingScreenHandler(
        Screen.BLESSING_CHOICE, _decide_blessing_choice,
        parse_fn=parse_blessing_choice, parse_needs_image=True, ocr_prefixes=["blessing"],
    ),
    Screen.JOURNEY_START: DelegatingScreenHandler(
        Screen.JOURNEY_START, _decide_journey_start,
        parse_fn=parse_journey_start, ocr_prefixes=["journey_start"],
    ),
    Screen.CONFIRM_DIALOG: DelegatingScreenHandler(
        Screen.CONFIRM_DIALOG, _decide_confirm_dialog,
        parse_fn=parse_confirm_dialog, ocr_prefixes=["confirm_dialog"],
    ),
    Screen.EVENT_FAST_FORWARD_SETTING: DelegatingScreenHandler(
        Screen.EVENT_FAST_FORWARD_SETTING, _decide_event_fast_forward_setting,
        parse_fn=parse_event_fast_forward_setting, parse_needs_image=True,
        ocr_prefixes=["event_fast_forward"],
    ),
    Screen.RELIC_CHOICE: DelegatingScreenHandler(
        Screen.RELIC_CHOICE, _decide_relic_choice,
        parse_fn=parse_relic_choice, parse_needs_image=True, ocr_prefixes=["relic_choice"],
    ),
    Screen.BATTLE: DelegatingScreenHandler(
        Screen.BATTLE, _decide_battle,
        parse_fn=parse_battle, parse_needs_image=True, ocr_prefixes=["battle"],
    ),
    Screen.SKILL_SELECT: DelegatingScreenHandler(
        Screen.SKILL_SELECT, _decide_skill_select,
        parse_fn=parse_skill_select, ocr_prefixes=["skill_select"],
    ),
    Screen.REGION_MOVE: DelegatingScreenHandler(
        Screen.REGION_MOVE, _decide_region_move,
        parse_fn=parse_region_move, ocr_prefixes=["region_move"],
    ),
}

# Ordered list of handlers carrying a 1.0/0.90 anchor signature, in the exact
# order the old _match_screen checked them.
ANCHOR_HANDLERS: list[DelegatingScreenHandler] = sorted(
    (h for h in HANDLERS.values() if h._anchor_fn is not None),
    key=lambda h: h.priority,
)
