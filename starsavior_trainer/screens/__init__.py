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
    _has_battle_signature,
    _has_commission_select_signature,
    _has_dialogue_signature,
    _has_event_choice_signature,
    _has_filter_dialog_signature,
    _has_game_menu_signature,
    _has_goal_list_signature,
    _has_initial_signature,
    _has_main_menu_panel_signature,
    _has_main_screen_signature,
    _has_region_move_signature,
    _has_post_training_signature,
    _has_rest_submenu_signature,
    _has_reward_signature,
    _has_shop_signature,
    _has_support_card_detail_signature,
    _has_support_friend_list_signature,
    _has_support_picker_signature,
    _has_training_hub_shop_signature,
    _has_training_select_signature,
)
from starsavior_trainer.prejourney import (
    decide_filter_dialog,
    decide_initial_with_difficulty,
    decide_main_menu_panel,
    decide_main_screen,
    decide_support_card_detail,
    decide_support_friend_list,
    decide_support_picker,
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
    Rect,
    RelicChoice,
    RelicOption,
    RestSubmenu,
    Screen,
    ShopItem,
    ShopScene,
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
    parse_filter_dialog,
    parse_journey_start,
    parse_main_menu_panel,
    parse_main_screen,
    parse_post_training,
    parse_region_move,
    parse_relic_choice,
    parse_rest_submenu,
    parse_shop,
    parse_support_card_detail,
    parse_support_friend_list,
    parse_support_picker,
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
    # 赛前流程增强: 配置了难度时先点难度按钮再点开始; 无配置时与旧行为一致。
    return decide_initial_with_difficulty(obs, state, policy)


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
    # 2026-06-12 用户拍板: 支援卡(卡组/好友卡)由用户人工配置, bot 不碰 ——
    # 这个画面永远直接点「旅程起点」。SUPPORT_* 三画面保留识别仅作误入自愈。
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
    return Action("click", policy.config.skip_button, "dialogue screen, click skip", repeat=3)


def _decide_training_hub(obs, state, policy):
    if isinstance(obs.payload, TrainingHubStatus):
        # D-DAY 评鉴战日: 大厅变成「评鉴战」+「交易」(取代 训练/委托/休息)。必须先逛
        # 交易(打过评鉴战交易就消失)、再去评鉴战。_dday_trading_done 由 decide_shop 逛完置位。
        if obs.payload.rating_battle_button is not None:
            if not policy._dday_trading_done and obs.payload.trading_button is not None:
                return Action("click", obs.payload.trading_button, "D-DAY 大厅: 先去交易")
            return Action("click", obs.payload.rating_battle_button, "D-DAY 大厅: 去评鉴战")
        # Not a D-DAY hub → an ordinary turn. Clear the one-shot trading flag so the
        # NEXT 评鉴战 day shops again before its battle.
        policy._dday_trading_done = False
        # If we just bailed out of TRAINING_SELECT because every option's fail rate
        # was too high (low stamina), rest now instead of re-entering training —
        # otherwise hub<->training_select would loop forever. One-shot flag.
        if getattr(policy, "_needs_rest", False):
            policy._needs_rest = False
            if obs.payload.rest_button is not None:
                return Action("click", obs.payload.rest_button, "low stamina (all training too risky), rest")
        if obs.payload.has_commission_alert and obs.payload.commission_button is not None:
            return Action("click", obs.payload.commission_button, "training hub, commission alert")
        if obs.payload.has_shop_alert and obs.payload.shop_button is not None:
            return Action("click", obs.payload.shop_button, "training hub, shop alert")
        # 技能学习留到跑马完成后(前期学技能不影响跑马),大厅前期不中途进技能界面。
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
        return policy.decide_relic_choice(obs.payload, state)
    if not _is_iterable_of(obs.payload, RelicOption):
        # relic_choice 分类但 parse 不出选项 → 多半是被误判的"奖励/结果展示"(委托 SUCCESS、
        # 评鉴战奖励纯展示 等点任意处继续的全屏页)。点屏幕中心推进, 别 pause 卡死。
        return Action("click", policy.config.screen_center, "relic screen no options, click center to advance")
    return policy.decide_relic(obs.payload)


def _decide_commission_select(obs, state, policy):
    if not isinstance(obs.payload, CommissionChoice):
        policy._pending_commission = None
        return Action("pause", None, "commission screen missing options")
    return policy.decide_commission(obs.payload, state)


def _decide_shop(obs, state, policy):
    # Fallback decision (blue mode / no inspector). The live loop normally drives
    # the shop via ShopInspector (reads each item's effect by clicking it); here we
    # just decide on whatever item effects we already have.
    if isinstance(obs.payload, ShopScene):
        return policy.decide_shop(obs.payload.items)
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
    if state.allow_skill_learning and _is_iterable_of(obs.payload, SkillOption):
        return policy.decide_skill(obs.payload, state)
    # 技能学习留到跑马完成后:前期进了技能/潜质界面就点右上角 ✕ 退出,不在前期学技能。
    return Action("click", policy.config.skill_select_close_button, "skill select: 前期不学技能, 点 ✕ 退出")


def _decide_post_training(obs, state, policy):
    if isinstance(obs.payload, PostTrainingResult) and obs.payload.skip_button is not None:
        return Action("click", obs.payload.skip_button, "post-training, click skip")
    return Action("click", policy.config.skip_button, "post-training, click skip")


def _decide_region_move(obs, state, policy):
    # Click the target the parser found: a destination row (列车月台 → 选目的地) or
    # the 前往 button once a destination is selected. The old code clicked a fixed
    # config.move_button that hit the character art and stalled.
    if not isinstance(obs.payload, Rect):
        return Action("pause", None, "region move screen, no target parsed")
    return Action("click", obs.payload, "region move: 选目的地/前往")


def _decide_game_menu(obs, state, policy):
    # Accidental 菜单 popup: click ✕ to close and return to the underlying screen.
    # Never the generic centre-click advance — the centre holds 重新观测/观测结束,
    # which would restart or end the run.
    return Action(
        "click",
        policy.config.game_menu_close_button,
        "game menu popup, click ✕ to close (avoid centre 重新观测/观测结束)",
    )


def _decide_reward(obs, state, policy):
    # 获得奖励 popup: the centre relic card is a dead click zone — only the
    # "点击以继续" prompt advances. Click it; the live loop re-captures quickly
    # (advance-screen short sleep) so sequential popups blow through fast.
    return Action(
        "click",
        policy.config.reward_continue_button,
        "reward obtained (获得奖励), click 点击以继续 to advance",
    )


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
        # Only the selected item's effect detail needs OCR — the row click targets
        # come from the region profile, and names/prices OCR unreliably and aren't
        # used for the buy decision (which keys off the effect). The shop inspector
        # clicks each row to reveal its effect in this one detail region.
        parse_fn=parse_shop, parse_needs_image=True, ocr_prefixes=["shop_detail"],
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
        # parse_needs_image: 卡组指示圆点要看像素亮度(赛前卡组切换)。
        parse_fn=parse_journey_start, parse_needs_image=True, ocr_prefixes=["journey_start"],
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
        Screen.BATTLE, _decide_battle, priority=10,
        # 基础评鉴战 entry confirm needs an OCR signature (跳过战斗 + 评鉴战 title) so it
        # doesn't fall through to the blue-button fallback (→ event_fast_forward).
        # Priority 10 = checked after the other signatures (it's specific enough not
        # to collide), still before the fallback anchor-text scoring.
        anchor_fn=_has_battle_signature, anchor_confidence=1.0,
        parse_fn=parse_battle, parse_needs_image=True, ocr_prefixes=["battle"],
    ),
    Screen.SKILL_SELECT: DelegatingScreenHandler(
        Screen.SKILL_SELECT, _decide_skill_select,
        parse_fn=parse_skill_select, ocr_prefixes=["skill_select"],
    ),
    Screen.REGION_MOVE: DelegatingScreenHandler(
        Screen.REGION_MOVE, _decide_region_move, priority=6,
        # 列车月台 region-move needs a signature (地区移动 + 列车月台) so it pre-empts
        # the relic_choice fallback that otherwise mis-scored it and stalled.
        anchor_fn=_has_region_move_signature, anchor_confidence=1.0,
        parse_fn=parse_region_move, ocr_prefixes=["region_move"],
    ),
    # 获得奖励 reward popup. Priority 2 (before DIALOGUE=4) so its unique centre
    # title pre-empts any accidental dialogue/character_select match. No parse_fn
    # — the policy clicks a fixed continue button.
    Screen.REWARD: DelegatingScreenHandler(
        Screen.REWARD, _decide_reward, priority=2,
        anchor_fn=_has_reward_signature, anchor_confidence=1.0,
        parse_fn=None, ocr_prefixes=None,
    ),
    # Accidental 菜单 popup. Priority 2 (checked early) so it pre-empts any
    # background screen whose anchors are still partly visible behind the dialog.
    # Its 菜单-title + 观测-row signature is unique, so it never steals a normal
    # screen. No parse_fn — the policy clicks the fixed ✕ close button.
    # 赛前流程入口(docs/prejourney-flow.md)。priority 排在所有局内画面之后:
    # 主界面/菜单栏只在开局阶段出现, 签名词组合(战斗+管理…/旅程+商店…)足够特异。
    # 注意: 菜单面板只盖右侧 2/3, 左侧菜单列仍可见 → 面板(11)必须先于主界面(12)
    # 检查, 否则面板开着时被认成主界面、反复点菜单按钮(实机帧验证过这个误判)。
    Screen.MAIN_SCREEN: DelegatingScreenHandler(
        Screen.MAIN_SCREEN, decide_main_screen, priority=12,
        anchor_fn=_has_main_screen_signature, anchor_confidence=1.0,
        parse_fn=parse_main_screen, ocr_prefixes=["main_screen"],
    ),
    # 筛选弹窗覆盖在角色选择/刻印操作上层 —— priority=1 抢在底层画面标题锚之前,
    # 否则弹窗开着时还会被认成底层画面去点列表(点不到, 弹窗挡着)。
    Screen.FILTER_DIALOG: DelegatingScreenHandler(
        Screen.FILTER_DIALOG, decide_filter_dialog, priority=1,
        anchor_fn=_has_filter_dialog_signature, anchor_confidence=1.0,
        # OCR bbox 定位按钮(弹窗可拖动滚动, 固定坐标不可靠), 需要 image+ocr。
        parse_fn=parse_filter_dialog, parse_needs_image=True, parse_needs_ocr=True,
        ocr_prefixes=["filter_dialog"],
    ),
    Screen.MAIN_MENU_PANEL: DelegatingScreenHandler(
        Screen.MAIN_MENU_PANEL, decide_main_menu_panel, priority=11,
        anchor_fn=_has_main_menu_panel_signature, anchor_confidence=1.0,
        parse_fn=parse_main_menu_panel, ocr_prefixes=["main_menu_panel"],
    ),
    # 「达成目标列表」黑底展示页: 点底部「点击以继续」推进(与获得奖励的
    # 继续提示几乎同位, 复用 reward_continue_button)。
    Screen.GOAL_LIST: DelegatingScreenHandler(
        Screen.GOAL_LIST,
        lambda obs, state, policy: Action(
            "click", policy.config.reward_continue_button, "goal list shown, click 点击以继续", repeat=2,
        ),
        priority=16,
        anchor_fn=_has_goal_list_signature, anchor_confidence=1.0,
    ),
    # 好友卡流程三画面(标题与旅程起点共用): 好友卡墙(可借用次数)必须排在
    # 支援卡选择(可借用)之前, 否则「可借用次数」也含「可借用」会被截胡。
    Screen.SUPPORT_FRIEND_LIST: DelegatingScreenHandler(
        Screen.SUPPORT_FRIEND_LIST, decide_support_friend_list, priority=13,
        anchor_fn=_has_support_friend_list_signature, anchor_confidence=1.0,
        parse_fn=parse_support_friend_list, ocr_prefixes=["support_friend"],
    ),
    Screen.SUPPORT_PICKER: DelegatingScreenHandler(
        Screen.SUPPORT_PICKER, decide_support_picker, priority=14,
        anchor_fn=_has_support_picker_signature, anchor_confidence=1.0,
        parse_fn=parse_support_picker, ocr_prefixes=["support_picker"],
    ),
    Screen.SUPPORT_CARD_DETAIL: DelegatingScreenHandler(
        Screen.SUPPORT_CARD_DETAIL, decide_support_card_detail, priority=15,
        anchor_fn=_has_support_card_detail_signature, anchor_confidence=1.0,
        parse_fn=parse_support_card_detail, ocr_prefixes=["support_card_detail"],
    ),
    Screen.GAME_MENU: DelegatingScreenHandler(
        Screen.GAME_MENU, _decide_game_menu, priority=2,
        anchor_fn=_has_game_menu_signature, anchor_confidence=1.0,
        parse_fn=None, ocr_prefixes=None,
    ),
}

# Ordered list of handlers carrying a 1.0/0.90 anchor signature, in the exact
# order the old _match_screen checked them.
ANCHOR_HANDLERS: list[DelegatingScreenHandler] = sorted(
    (h for h in HANDLERS.values() if h._anchor_fn is not None),
    key=lambda h: h.priority,
)
