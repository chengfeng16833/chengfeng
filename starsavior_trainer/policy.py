from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from starsavior_trainer.models import (
    Action,
    BattleScene,
    BlessingChoice,
    SkillOption,
    BlessingOption,
    BlessingSetup,
    CharacterOption,
    CharacterSelect,
    CommissionChoice,
    CommissionOption,
    ConfirmDialog,
    DialogueScene,
    EventOption,
    EventFastForwardSetting,
    GameState,
    Observation,
    Rect,
    JourneyStart,
    RelicChoice,
    RelicOption,
    RestSubmenu,
    Screen,
    ShopItem,
    TrainingChoice,
    TrainingHubStatus,
)
from starsavior_trainer.screen_reader import PostTrainingResult, parse_first_int


DEFAULT_EVENT_KEYWORDS = {
    "coin_cost": (
        "coin",
        "coins",
        "\u4ed8\u94b1",
        "\u91d1\u5e01",
        "\u8d2d\u4e70",
        "\u82b1\u94b1",
    ),
    "fatigue_cost": (
        "fatigue",
        "\u75b2\u52b3",
        "\u75b2\u52b3\u503c",
        "\u6d88\u8017\u75b2\u52b3",
        "\u7528\u529b\u91cf\u62d4",
        "\u7528\u529b\u91cf\u6273",
        "\u62d4\u51fa\u6765",
        "\u6273\u51fa\u6765",
    ),
    "recover": (
        "stamina",
        "recover",
        "\u4f53\u529b",
        "\u6062\u590d",
        "\u56de\u590d",
    ),
    "mood": (
        "mood",
        "\u5fc3\u60c5",
        "\u5e72\u52b2",
    ),
    "attribute": (
        "speed",
        "stamina",
        "power",
        "guts",
        "wisdom",
        "\u901f\u5ea6",
        "\u8010\u529b",
        "\u529b\u91cf",
        "\u6839\u6027",
        "\u667a\u529b",
        "\u5c5e\u6027",
    ),
}

# Generic rule profiles to fall back on when no build-profile rule matches.
# Order = preference. Conditional rules (low_stamina, gamble, need_*, \u2026) are
# skipped \u2014 we don't guess on situational conditions and defer to the keyword
# heuristic instead.
_EVENT_DEFAULT_PROFILES = ("default", "default_safe", "safe_mode")

# Max character-list scrolls before giving up (≈ half down, half up). The list is
# short enough that this fully covers it in each direction.
_CHARACTER_SCROLL_CAP = 30

_EVENTS_PATH = Path(__file__).resolve().parents[1] / "config" / "events.json"
_EVENT_DB_CACHE: list[dict] | None = None


def _load_event_db() -> list[dict]:
    """Load and cache config/events.json (list of event dicts). Empty on error."""
    global _EVENT_DB_CACHE
    if _EVENT_DB_CACHE is None:
        try:
            data = json.loads(_EVENTS_PATH.read_text(encoding="utf-8"))
            _EVENT_DB_CACHE = list(data.get("events", []))
        except (OSError, json.JSONDecodeError):
            _EVENT_DB_CACHE = []
    return _EVENT_DB_CACHE


def _match_event(ocr_title: str, events: list[dict]) -> dict | None:
    """Fuzzy-match an OCR'd event title to a database event.

    OCR mangles characters (\u8bad\u2192\u5ddd etc.), so score each event title/alias by the
    fraction of its characters present in the OCR text and take the best above a
    threshold.
    """
    norm = "".join(ch for ch in ocr_title if "\u4e00" <= ch <= "\u9fff")
    if len(norm) < 2:
        return None
    best: dict | None = None
    best_score = 0.0
    for event in events:
        names = [event.get("title", "")] + list(event.get("aliases") or [])
        for name in names:
            key = "".join(ch for ch in str(name) if "\u4e00" <= ch <= "\u9fff")
            if len(key) < 2:
                continue
            score = sum(1 for ch in key if ch in norm) / len(key)
            if score > best_score:
                best_score = score
                best = event
    return best if best_score >= 0.6 else None


def _event_recommended_index(event: dict, build_profile: str) -> int | None:
    """Return the 1-based option index recommended for this build, or None.

    Prefers an exact build-profile rule, then a generic default rule. Returns
    None for events that only carry situational/conditional rules.
    """
    rules = event.get("default_rules") or []
    for rule in rules:
        if rule.get("profile") == build_profile:
            return rule.get("choose_option")
    for fallback in _EVENT_DEFAULT_PROFILES:
        for rule in rules:
            if rule.get("profile") == fallback:
                return rule.get("choose_option")
    return None


@dataclass(frozen=True)
class PolicyConfig:
    min_screen_confidence: float = 0.75
    max_training_fail_rate: int = 30
    meditation_coin_threshold: int = 60
    lodging_coin_threshold: int = 30
    min_skill_points: int = 90
    ring_bonus: dict[str, int] = field(
        default_factory=lambda: {
            "rainbow": 40,
            "gold": 25,
            "blue": 10,
            "none": 0,
        }
    )
    shop_whitelist: dict[str, int] = field(
        default_factory=lambda: {
            "advanced_training_book": 120,
            "stamina_potion": 80,
            "mood_candy": 60,
        }
    )
    shop_aliases: dict[str, str] = field(
        default_factory=lambda: {
            "\u9ad8\u7ea7\u8bad\u7ec3\u4e66": "advanced_training_book",
            "\u4f53\u529b\u836f": "stamina_potion",
            "\u5fc3\u60c5\u7cd6": "mood_candy",
        }
    )
    # \u4ea4\u6613\u6309"\u6548\u679c\u8bf4\u660e"\u4e70(\u5546\u54c1\u540d\u4e0e\u6548\u679c\u65e0\u5173): \u6548\u679c\u6587\u672c\u542b\u8fd9\u4e9b\u5173\u952e\u8bcd\u5c31\u4e70 \u2014\u2014 \u56de\u590d\u4f53\u529b
    # \u7c7b + "\u6f5c\u8d28\u70b9\u6570N\u9000\u8fd8"(\u767d\u5ad6\u6f5c\u8d28\u70b9,\u542b\u56fa\u5b9a\u4e70\u7684\u624b\u6301\u98ce\u6247). \u4e0d\u5237\u65b0\u3001\u4e0d\u9650\u4ef7\u3002
    shop_buy_effect_keywords: tuple[str, ...] = (
        "\u56de\u590d\u4f53\u529b", "\u4f53\u529b", "\u8010\u529b", "\u6f5c\u8d28\u70b9", "\u9000\u8fd8",
    )
    # Internal stat keys map to the game's training types as:
    #   power=力量  stamina=体力(生命)  guts=韧性(防御)  wisdom=专注(命中)  speed=保护(命抗)
    # Power runs follow "力量/生命为主, 防御为辅": 力量 main, 体力 co-primary, 韧性
    # secondary; 专注/保护 stay at 0 (only worth it via support-card heads, which the
    # ring_bonus already rewards). Over-biasing 韧性/防御 would starve the main stat's
    # proficiency and miss the 1250 cap, so keep it modest.
    training_bias_by_profile: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "balanced": {},
            "power_focus": {"power": 18, "stamina": 12, "guts": 8},
            "focus_focus": {"wisdom": 18, "speed": 8},
            "durability_focus": {"stamina": 16, "guts": 10},
            "stamina_tank": {"stamina": 20, "guts": 12},
            "protection_focus": {"guts": 16, "stamina": 10},
        }
    )
    # Early-game (前12回合) bias: inside this round window, 力量(power)/生命(stamina)
    # get an extra score weight so the bot front-loads them. Added on top of the
    # profile bias (加权打分) — not a hard override, still compared against the rest.
    early_game_rounds: int = 12
    early_game_stat_weight: dict[str, int] = field(
        default_factory=lambda: {"power": 15, "stamina": 15}
    )
    # Early-game rings matter more (proficiency compounds), so amplify the
    # ring_bonus inside the early window. 1.0 = no amplification.
    early_ring_multiplier: float = 2.5
    # 组合圣遗物(队员全体)按部位属性 + build 优先级选: 在当前3张里选优先级最高的属性;
    # 优先级里都没出现则随便选(取第一张). 属性 key: attack/crit_rate/crit_dmg/hp/defense/hit/resist/speed.
    relic_attribute_priority_by_profile: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "power_focus": ("attack", "crit_rate", "crit_dmg"),
            "stamina_tank": ("hp", "defense", "attack", "crit_rate", "crit_dmg"),
        }
    )
    skill_keywords_by_profile: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "balanced": ("\u653b\u51fb", "\u96c6\u4e2d", "\u751f\u547d", "\u4fdd\u62a4", "\u6d1e\u5bdf"),
            "power_focus": ("\u653b\u51fb", "\u529b\u91cf", "attack", "power"),
            "focus_focus": ("\u96c6\u4e2d", "\u6d1e\u5bdf", "\u4e13\u6ce8", "focus", "wisdom"),
            "durability_focus": ("\u751f\u547d", "\u4fdd\u62a4", "\u4f53\u529b", "\u97e7\u6027", "stamina", "guts"),
            "stamina_tank": ("\u751f\u547d", "\u4f53\u529b", "stamina", "hp"),
            "protection_focus": ("\u4fdd\u62a4", "\u97e7\u6027", "protection", "guts"),
        }
    )
    blessing_attribute_by_profile: dict[str, str] = field(
        default_factory=lambda: {
            "balanced": "power",
            "power_focus": "power",
            "focus_focus": "wisdom",
            "durability_focus": "stamina",
            "stamina_tank": "stamina",
            "protection_focus": "guts",
        }
    )
    max_blessing_value: int = 50
    max_total_blessing_value: int = 100
    start_button: Rect = Rect(2040, 1318, 470, 75)
    skip_button: Rect = Rect(1740, 980, 120, 60)
    move_button: Rect = Rect(1580, 900, 220, 80)
    # "点击以继续" prompt on the 获得奖励 reward popup. The centre card is a dead
    # click zone; this bottom-centre prompt is the only spot that advances.
    reward_continue_button: Rect = Rect(1180, 1250, 230, 64)
    # 技能/潜质界面右上角 ✕ 关闭按钮(前期不学技能,进了就点它退出)。
    skill_select_close_button: Rect = Rect(2125, 300, 90, 66)
    # 屏幕中心: 用于推进"被误判成 relic_choice 的奖励/结果展示"(委托 SUCCESS、评鉴战
    # 奖励纯展示、阿尔克那等点任意处继续的全屏展示), 避免它们 parse 不出选项时 pause 卡死。
    screen_center: Rect = Rect(1180, 660, 200, 120)
    # 误触弹出的游戏「菜单」弹窗右上角 ✕ 关闭按钮。识别到菜单就点它关闭(自愈), 绝不点
    # 菜单中部的 重新观测/观测结束(会重开/结束本局)。坐标取自真帧 OCR 的 X 块中心。
    game_menu_close_button: Rect = Rect(1808, 535, 64, 60)


class TrainerPolicy:
    def __init__(self, config: PolicyConfig | None = None):
        self.config = config or PolicyConfig()
        self._pending_commission: Rect | None = None
        # Two-step relic confirm: remembers the relic card we clicked so the next
        # call clicks 确认 instead of re-evaluating "best" every frame. Without this
        # a normal relic choice never reached a confirm path (selected_name is only
        # set for the fixed initial relic), so it re-picked each frame and flipped
        # between near-scored cards — the back-and-forth oscillation.
        self._pending_relic: Rect | None = None
        # Same two-step confirm for blessing choice: equal-value cards can't be told
        # apart by selected_name (OCR), so confirming on selected_name==best never
        # fires → loop. Remember the card we clicked; next frame click 确认 directly.
        self._pending_blessing: Rect | None = None
        # Set when we bail out of TRAINING_SELECT because every option's fail rate
        # is too high; the next TRAINING_HUB decision consumes it to go rest.
        self._needs_rest: bool = False
        # Two-step rest: remembers the option we selected so the next call confirms.
        self._pending_rest: Rect | None = None
        # Character-list search state (bidirectional, bounded — avoids the
        # infinite one-direction scroll that missed a target above the start).
        self._char_scroll_count: int = 0
        self._char_scroll_down: bool = True
        self._char_reversed: bool = False
        self._char_seen_names: frozenset[str] | None = None
        # Two-step character confirm: remembers the desired character whose row we
        # just clicked, so the next call clicks 选择 to confirm — WITHOUT relying on
        # the left-panel selected-name OCR (which is unreliable for some characters).
        self._char_pending_confirm: str | None = None
        # D-DAY 评鉴战日: 是否已逛过交易(打过评鉴战交易就消失,所以先交易再评鉴战)。
        self._dday_trading_done: bool = False

    def decide(self, state: GameState, observation: Observation) -> Action:
        if observation.confidence < self.config.min_screen_confidence:
            return Action("pause", None, f"low screen confidence: {observation.confidence:.2f}")

        # Leaving the character-select screen ends any in-progress list search, so
        # a later visit (e.g. the next journey) starts a fresh bidirectional scan.
        if observation.screen != Screen.CHARACTER_SELECT:
            self._reset_character_scroll()
            self._char_pending_confirm = None
        # Forget any half-finished relic pick once we leave the relic screen.
        if observation.screen != Screen.RELIC_CHOICE:
            self._pending_relic = None
        if observation.screen != Screen.BLESSING_CHOICE:
            self._pending_blessing = None

        # Dispatch through the screen registry instead of a hardcoded if/elif
        # chain. Each handler.decide is a verbatim copy of the branch that used
        # to live here and receives this policy for config/instance-state access.
        # Imported lazily to avoid an import cycle (screens/__init__ imports policy).
        from starsavior_trainer.screens import HANDLERS

        handler = HANDLERS.get(observation.screen)
        if handler is None:
            return Action("pause", None, "unknown screen")
        return handler.decide(observation, state, self)

    def training_score(self, choice: TrainingChoice, state: GameState | None = None) -> float:
        # fail_rate is None when the card's 失败率 isn't shown (it isn't the selected
        # card) — i.e. UNKNOWN, not 0%. Never gamble on an un-inspected card: treat
        # unknown (and over-threshold) fail rates as un-trainable so the policy bails
        # to rest instead of training a card whose real fail rate could be ~99%.
        if choice.fail_rate is None or choice.fail_rate > self.config.max_training_fail_rate:
            return float("-inf")
        if choice.fail_rate <= 5:
            fail_penalty = 0
        elif choice.fail_rate <= 15:
            fail_penalty = choice.fail_rate * 1.5
        else:
            fail_penalty = choice.fail_rate * 3

        profile = state.build_profile if state else "balanced"
        strategic_bias = self.config.training_bias_by_profile.get(profile, {}).get(choice.name, 0)

        is_early_round = (
            state is not None
            and state.current_round is not None
            and state.current_round <= self.config.early_game_rounds
        )

        ring_value = self.config.ring_bonus.get(choice.ring, 0)
        early_bonus = 0
        if is_early_round:
            ring_value *= self.config.early_ring_multiplier
            early_bonus = self.config.early_game_stat_weight.get(choice.name, 0)

        return (
            choice.stat_gain
            + ring_value
            - fail_penalty
            + strategic_bias
            + early_bonus
        )

    def _reset_character_scroll(self) -> None:
        self._char_scroll_count = 0
        self._char_scroll_down = True
        self._char_reversed = False
        self._char_seen_names = None

    def decide_character_select(self, selection: CharacterSelect, state: GameState) -> Action:
        if state.desired_character:
            # Same-named characters now have multiple forms (普通 / ANOTHER / COSMIC),
            # told apart by the variant text under each row's class icon. Rank the
            # name-matching options by (exact-name first, then variant-match) and take
            # the best. So: a requested variant wins when present; with no variant
            # requested the plain form is preferred; but a single-form character whose
            # only form carries a COSMIC/ANOTHER tag is still selectable (fallback to
            # any variant) instead of being un-matchable.
            desired_variant = state.desired_variant or ""
            candidates = [
                opt
                for opt in selection.options
                if opt.name == state.desired_character
                or _character_name_matches(opt.name, state.desired_character)
            ]
            candidates.sort(
                key=lambda o: (
                    0 if o.name == state.desired_character else 1,  # exact name before substring
                    0 if (o.variant or "") == desired_variant else 1,  # then variant match
                )
            )
            match = candidates[0] if candidates else None
            if match is not None:
                self._reset_character_scroll()
                # Confirm if the game shows her selected, OR if we already clicked
                # her row last turn — the click works even when the left-panel name
                # OCR can't verify it, so a remembered click is enough to proceed.
                if match.selected or self._char_pending_confirm == match.name:
                    self._char_pending_confirm = None
                    return Action("click", selection.confirm_button, f"confirm desired character {match.name}")
                # First sighting: click her row to select, and remember we did so.
                self._char_pending_confirm = match.name
                return Action("click", match.target, f"select desired character {match.name}")

            # Not visible — clear the pending confirm (she scrolled out of view) and
            # search the list in BOTH directions (the target may be above the start).
            # Scroll down first, then reverse to up when we hit the list end (view
            # stops changing) or at the halfway cap.
            self._char_pending_confirm = None
            scroll_target = _character_list_scroll_target(selection)
            current_names = frozenset(option.name for option in selection.options)
            if scroll_target is not None and selection.can_scroll and self._char_scroll_count < _CHARACTER_SCROLL_CAP:
                # Reverse direction exactly once: when the list stops changing (end
                # reached) or at the halfway cap, whichever comes first. Reversing
                # only once avoids oscillating in place if a scroll doesn't move.
                end_reached = self._char_seen_names is not None and current_names == self._char_seen_names
                if not self._char_reversed and (end_reached or self._char_scroll_count >= _CHARACTER_SCROLL_CAP // 2):
                    self._char_scroll_down = not self._char_scroll_down
                    self._char_reversed = True
                self._char_seen_names = current_names
                self._char_scroll_count += 1
                clicks = -3 if self._char_scroll_down else 3
                direction = "down" if self._char_scroll_down else "up"
                return Action(
                    "scroll",
                    scroll_target,
                    f"scroll character list {direction} to find: {state.desired_character}",
                    scroll_clicks=clicks,
                )
            # Searched the whole list both ways (or can't scroll) and still no match.
            # Stay paused (do NOT reset here) so we stop instead of looping; leaving
            # the screen resets the search state for the next visit.
            return Action("pause", None, f"desired character not found after scrolling: {state.desired_character}")

        selected = _selected_character(selection.options, selection.selected_name)
        if selected is not None:
            return Action("click", selection.confirm_button, f"confirm selected character {selected.name}")

        return Action("pause", None, "no selected character recognized")

    def decide_blessing_setup(self, setup: BlessingSetup) -> Action:
        empty_slots = [slot for slot in setup.slots if not slot.occupied]
        if empty_slots:
            first = sorted(empty_slots, key=lambda slot: slot.index)[0]
            return Action("click", first.target, f"open blessing slot {first.index}")
        if setup.can_confirm:
            return Action("click", setup.confirm_button, "all blessing slots filled, confirm")
        return Action("pause", None, "all blessing slots filled but confirm is disabled")

    def decide_blessing_choice(self, choice: BlessingChoice, state: GameState) -> Action:
        # Two-step confirm: we clicked a blessing last frame — confirm it now instead
        # of re-picking. Same-value cards are indistinguishable by selected_name (OCR),
        # and the sub-blessing count flickers frame-to-frame, so the old "confirm when
        # selected_name==best" never fired reliably and looped. Lock the first pick.
        if self._pending_blessing is not None and choice.confirm_button is not None:
            target = self._pending_blessing
            self._pending_blessing = None
            return Action("click", target, "confirm chosen blessing")

        attribute = state.desired_blessing_attribute or self.config.blessing_attribute_by_profile.get(state.build_profile, "power")
        matching = [option for option in choice.options if option.attribute == attribute and option.value is not None]
        if not matching:
            return Action("pause", None, f"no {attribute} blessing option with recognized value")

        # Highest value wins; ties broken by position (topmost-leftmost) — NOT by
        # sub-blessing count, which OCR can't read reliably (equal-value cards are
        # near-identical in worth, so any consistent tiebreak avoids the flicker loop).
        best = max(matching, key=self.blessing_score)
        if choice.confirm_button is not None:
            self._pending_blessing = choice.confirm_button
        return Action(
            "click",
            best.target,
            f"choose {attribute} blessing: {best.name}={best.value}",
        )

    def blessing_score(self, option: BlessingOption) -> tuple[int, int, int, str]:
        value = option.value if option.value is not None else -1
        return (value, -option.target.y, -option.target.x, option.name)

    def decide_journey_start(self, journey: JourneyStart) -> Action:
        return Action("click", journey.start_button, "arcana is fixed, click journey start")

    def decide_confirm_dialog(self, dialog: ConfirmDialog) -> Action:
        return Action("click", dialog.confirm_button, f"confirm dialog: {dialog.title}")

    def decide_event_fast_forward_setting(self, setting: EventFastForwardSetting) -> Action:
        if setting.selected_mode == "all_events":
            return Action("click", setting.confirm_button, "confirm fast-forward all events")
        return Action("click", setting.all_events_option, "select fast-forward all events")

    def decide_dialogue(self, dialogue: DialogueScene) -> Action:
        # A small, calm burst of skip taps per frame (the executor paces them at
        # ~5 Hz). Enough to blow through multi-line dialogue and dismiss a "skip?"
        # confirm, without the frantic over-clicking that overshoots into the next
        # screen.
        return Action("click", dialogue.skip_button, f"dialogue {dialogue.variant}, click skip", repeat=3)

    def decide_training(self, choices: Iterable[TrainingChoice], state: GameState | None = None) -> Action:
        ranked = sorted(
            ((self.training_score(choice, state), choice) for choice in choices),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked:
            return Action("pause", None, "no training choices recognized")

        score, best = ranked[0]
        if score == float("-inf"):
            # Every training's fail rate is too high (low stamina). Don't get stuck:
            # go back to the training hub via the top-left back arrow, where the
            # hub-level decision will route to rest (the fail-rate threshold only
            # applies on TRAINING_SELECT, not the hub).
            back_button = next((c.back_button for _, c in ranked if c.back_button is not None), None)
            if back_button is not None:
                self._needs_rest = True  # hub will consume this to choose rest
                return Action("click", back_button, "all training fail rates too high, return to hub to rest")
            return Action("pause", None, "all training choices exceed failure threshold")

        # Two-step flow: first click the desired card to select it (the game then
        # reveals its 失败率 and预计增益), then click the 训练 confirm button to run it.
        if best.selected and best.confirm_button is not None:
            return Action(
                "click",
                best.confirm_button,
                f"confirm training {best.name}: score={score:.1f}, ring={best.ring}, fail={best.fail_rate}%",
            )
        return Action(
            "click",
            best.target,
            f"select {best.name}: score={score:.1f}, ring={best.ring}, fail={best.fail_rate}%",
        )

    def decide_rest(self, rest: RestSubmenu) -> Action:
        # Pick the best affordable option: 冥想室 (60, full restore) > 住处 (30,
        # decent restore + mood) > 露宿 (free, but may lower mood — last resort).
        if rest.coins >= self.config.meditation_coin_threshold and rest.has_meditation_room and rest.meditation_room is not None:
            target, label = rest.meditation_room, "meditation_room"
        elif rest.coins >= self.config.lodging_coin_threshold and rest.lodging is not None:
            target, label = rest.lodging, "lodging"
        else:
            target, label = rest.rough_sleep, "rough_sleep"

        # Two-step flow: select the option, then click the 休息 confirm button.
        # Without a confirm button (e.g. uncalibrated), fall back to a single click.
        if rest.confirm_button is None:
            return Action("click", target, f"rest: {label}")
        if self._pending_rest == target:
            self._pending_rest = None
            return Action("click", rest.confirm_button, f"confirm rest: {label}")
        self._pending_rest = target
        return Action("click", target, f"select rest: {label}")

    def event_priority(self, option: EventOption) -> tuple[int, str]:
        text = option.text.lower()
        if any(keyword.lower() in text for keyword in DEFAULT_EVENT_KEYWORDS["fatigue_cost"]):
            return -1000, "avoid fatigue cost"
        if any(keyword.lower() in text for keyword in DEFAULT_EVENT_KEYWORDS["coin_cost"]):
            return 400, "spend coins"
        if any(keyword.lower() in text for keyword in DEFAULT_EVENT_KEYWORDS["recover"]):
            return 300, "recover stamina"
        if any(keyword.lower() in text for keyword in DEFAULT_EVENT_KEYWORDS["mood"]):
            return 200, "improve mood"
        if any(keyword.lower() in text for keyword in DEFAULT_EVENT_KEYWORDS["attribute"]):
            return 100, "gain attributes"
        return 0, "unknown option"

    # Profiles that prefer the "survival/生存" branch in attack-vs-survival events
    # (e.g. 训练的方向性, 身份不明的商人). All others take the "attack/攻击" branch.
    _SURVIVAL_PROFILES = ("stamina_tank", "durability_focus", "protection_focus")

    def _event_db_choice(
        self, options: list[EventOption], state: GameState | None
    ) -> tuple[EventOption, str] | None:
        """Look the event up in config/events.json and return its recommended option.

        Matches the OCR'd event title to a database event, then maps the build
        profile's recommended choose_option (1-based, top-to-bottom) onto the
        parsed on-screen options (also top-to-bottom). None if no match.
        """
        if not options:
            return None
        title = options[0].event_title
        if not title:
            return None
        event = _match_event(title, _load_event_db())
        if event is None:
            return None
        profile = state.build_profile if state else "balanced"
        index = _event_recommended_index(event, profile)
        if index is None or not (1 <= index <= len(options)):
            return None
        reason = f"event db: {event.get('title', '')} build={profile} -> option {index}"
        return options[index - 1], reason

    def _build_orientation_choice(
        self, options: list[EventOption], state: GameState | None
    ) -> tuple[EventOption, str] | None:
        """For attack-vs-survival branching events, pick by the character build.

        These events (training direction, mystic-book merchant, …) offer an
        attack option and a survival option; the right pick is determined by the
        build profile, not generic keywords.
        """
        if state is None:
            return None
        attack = next((o for o in options if ("攻击" in o.text or "攻撃" in o.text)), None)
        survival = next((o for o in options if "生存" in o.text), None)
        if attack is None or survival is None:
            return None
        if state.build_profile in self._SURVIVAL_PROFILES:
            return survival, f"build {state.build_profile} -> survival training"
        return attack, f"build {state.build_profile} -> attack training"

    def decide_event(self, options: Iterable[EventOption], state: GameState | None = None) -> Action:
        options = list(options)

        # 1) Event database lookup: match the OCR'd title, pick the option its
        #    default_rules recommend for this build profile.
        db_choice = self._event_db_choice(options, state)
        if db_choice is not None:
            choice, reason = db_choice
            return Action("click", choice.target, f"{reason}: {choice.text}")

        # 2) Generic attack-vs-survival branch fallback (events not in the DB).
        oriented = self._build_orientation_choice(options, state)
        if oriented is not None:
            choice, reason = oriented
            return Action("click", choice.target, f"{reason}: {choice.text}")

        ranked = sorted(
            ((self.event_priority(option), option) for option in options),
            key=lambda item: item[0][0],
            reverse=True,
        )
        if not ranked:
            return Action("pause", None, "no event options recognized")

        (score, reason), best = ranked[0]
        return Action("click", best.target, f"{reason}: {best.text}", confidence=0.7 if score == 0 else 1.0)

    def decide_relic(self, options: Iterable[RelicOption]) -> Action:
        scored = [option for option in options if option.score is not None]
        if not scored:
            return Action("pause", None, "no relic score recognized")
        best = max(scored, key=lambda option: option.score or 0)
        return Action("click", best.target, f"highest relic score: {best.name}={best.score}")

    def decide_relic_choice(self, choice: RelicChoice, state: GameState | None = None) -> Action:
        if choice.selected_name and choice.confirm_button is not None:
            self._pending_relic = None
            return Action("click", choice.confirm_button, f"confirm selected relic {choice.selected_name}")

        # Two-step: we clicked a relic last frame — confirm it now instead of
        # re-evaluating. Re-picking every frame let the choice flip between
        # near-scored cards (OCR score noise on the highlighted card), so the bot
        # oscillated and never confirmed. Locking the first pick + confirming
        # breaks that loop and gives the missing confirm path for normal choices.
        if self._pending_relic is not None and choice.confirm_button is not None:
            self._pending_relic = None
            return Action("click", choice.confirm_button, "confirm chosen relic")

        if choice.fixed_name:
            for option in choice.options:
                if option.name == choice.fixed_name:
                    self._pending_relic = option.target
                    return Action("click", option.target, f"choose fixed relic {option.name}")
            return Action("pause", None, f"fixed relic not visible: {choice.fixed_name}")

        # Combo relics (队员全体): pick by the build's part/attribute priority, not by score.
        combo = self._combo_relic_pick(choice.options, state)
        if combo is not None:
            self._pending_relic = combo.target
            profile = state.build_profile if state else "balanced"
            return Action("click", combo.target, f"combo relic by build {profile}: {combo.name}({combo.attribute})")

        action = self.decide_relic(choice.options)
        if action.kind == "click":
            self._pending_relic = action.target
        return action

    def _combo_relic_pick(self, options: Iterable[RelicOption], state: GameState | None) -> RelicOption | None:
        """组合圣遗物(全部 is_team 且带 attribute)→ 按 build 属性优先级选;否则 None(回落到 decide_relic 按分数)."""
        opts = list(options)
        team = [o for o in opts if o.is_team and o.attribute]
        if not team or len(team) < len(opts):
            return None
        profile = state.build_profile if state else "balanced"
        priority = self.config.relic_attribute_priority_by_profile.get(profile, ())
        for attr in priority:
            for option in team:
                if option.attribute == attr:
                    return option
        return team[0]  # 优先级里都没出现 → 随便选第一张

    def decide_commission(self, choice: CommissionChoice, state: GameState) -> Action:
        # The red 受理讨伐委托 banner on the training hub is the gate that sends us
        # here, so on this screen we accept a doable commission. The commission
        # list is ordered by tier (低阶/中阶/高阶); the lowest tier is always within
        # the character's rank, so prefer it for a guaranteed-completable reward.
        if not choice.options:
            self._pending_commission = None
            if choice.back_button is not None:
                return Action("click", choice.back_button, "no commission listed, exit")
            return Action("pause", None, "no commission options recognized")

        # If any commission is flagged suitable (red), honor that first.
        suitable = [option for option in choice.options if option.has_red_text]
        if suitable:
            best = suitable[0]
        elif state.character_rank is not None:
            # Pick the HIGHEST-tier commission we can still do: the one whose 建议综合
            # 等级 (suggested rank, a number) is highest but still ≤ our character rank.
            # (User: at rank 21 we should take a mid-tier, not always the lowest I.)
            doable = [
                (rank, option)
                for option in choice.options
                if (rank := parse_first_int(option.rank)) is not None and rank <= state.character_rank
            ]
            best = max(doable, key=lambda item: item[0])[1] if doable else choice.options[0]
        else:
            # Unknown character rank → conservatively take the lowest-tier (first) entry.
            best = choice.options[0]
        if self._pending_commission == best.target and choice.accept_button is not None:
            self._pending_commission = None
            return Action("click", choice.accept_button, f"accept commission: {best.name}")
        self._pending_commission = best.target
        return Action("click", best.target, f"select commission: {best.name}")

    def shop_item_worth_buying(self, item: ShopItem) -> bool:
        # 按"效果说明"判断(商品名与效果无关): 效果含想要关键词(回复体力 / 潜质点数退还)
        # 就买。手持风扇效果是"伤害+1%"但含"潜质点数N退还"→ 仍买(白嫖潜质点)。
        effect = item.effect or ""
        return any(kw in effect for kw in self.config.shop_buy_effect_keywords)

    def choose_shop_item(self, items: Iterable[ShopItem]) -> ShopItem | None:
        # 返回第一个值得买的商品(按效果), 没有则 None。供 decide_shop 与 shop 检视器复用。
        for item in items:
            if self.shop_item_worth_buying(item):
                return item
        return None

    def decide_shop(self, items: Iterable[ShopItem]) -> Action:
        # 按"效果说明"买(商品名与效果无关), 不刷新、不限价: 效果含想要关键词就买; 都不含 → 退出.
        chosen = self.choose_shop_item(items)
        if chosen is not None:
            return Action("click", chosen.target, f"buy {chosen.name}: {(chosen.effect or '').strip()}")
        self._dday_trading_done = True  # 逛完交易 → D-DAY 大厅就去评鉴战
        return Action("skip", None, "交易: 没有想买的(回体力/潜质点退还), 退出")

    def skill_score(self, option: SkillOption, state: GameState) -> float:
        if option.target is None:
            return float("-inf")

        text = f"{option.name} {option.effect or ''}".lower()
        if "\u5df2\u4e60\u5f97" in text or "learned" in text:
            return float("-inf")

        keywords = self.config.skill_keywords_by_profile.get(
            state.build_profile,
            self.config.skill_keywords_by_profile["balanced"],
        )
        score = 0.0
        for index, keyword in enumerate(keywords):
            if keyword.lower() in text:
                score += 100 - index * 5

        if option.cost is not None:
            score -= option.cost / 100
        return score

    def decide_skill(self, options: Iterable[SkillOption], state: GameState) -> Action:
        ranked = sorted(
            ((self.skill_score(option, state), option) for option in options),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked:
            return Action("pause", None, "no skill options recognized")

        score, best = ranked[0]
        if score == float("-inf"):
            return Action("pause", None, "no learnable skill option recognized")
        return Action(
            "click",
            best.target,
            f"learn skill {best.name}: score={score:.1f}, cost={best.cost}",
        )


def _is_iterable_of(value: object, item_type: type) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    return all(isinstance(item, item_type) for item in value)


def _selected_character(options: Iterable[CharacterOption], selected_name: str | None) -> CharacterOption | None:
    for option in options:
        if option.selected or (selected_name is not None and option.name == selected_name):
            return option
    return None


def _character_name_matches(option_name: str | None, desired: str) -> bool:
    """Tolerant character-name match.

    True when the option name and the desired name are equal, or when one
    contains the other after stripping whitespace and the '·' separator.  The
    shorter side must be at least 2 characters so a single-character name does
    not over-match unrelated entries.
    """
    if not option_name:
        return False

    def _norm(text: str) -> str:
        return text.replace(" ", "").replace("·", "").replace("・", "").strip()

    a = _norm(option_name)
    b = _norm(desired)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 2 and shorter in longer


def _character_list_scroll_target(selection: CharacterSelect) -> Rect | None:
    """Return a rect inside the character list suitable as a scroll anchor.

    Prefers the middle option (index 3) so the scroll gesture lands at the
    centre of the visible list.  Falls back to the first non-confirm option.
    """
    list_options = [opt for opt in selection.options if not opt.selected]
    if not list_options:
        return None
    mid = list_options[len(list_options) // 2]
    return mid.target
