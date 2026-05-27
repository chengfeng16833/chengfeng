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
from starsavior_trainer.screen_reader import PostTrainingResult


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
    training_bias_by_profile: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "balanced": {},
            "power_focus": {"power": 18, "speed": 8},
            "focus_focus": {"wisdom": 18, "speed": 8},
            "durability_focus": {"stamina": 16, "guts": 10},
            "stamina_tank": {"stamina": 20, "guts": 12},
            "protection_focus": {"guts": 16, "stamina": 10},
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


class TrainerPolicy:
    def __init__(self, config: PolicyConfig | None = None):
        self.config = config or PolicyConfig()
        self._pending_commission: Rect | None = None
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

    def decide(self, state: GameState, observation: Observation) -> Action:
        if observation.confidence < self.config.min_screen_confidence:
            return Action("pause", None, f"low screen confidence: {observation.confidence:.2f}")

        # Leaving the character-select screen ends any in-progress list search, so
        # a later visit (e.g. the next journey) starts a fresh bidirectional scan.
        if observation.screen != Screen.CHARACTER_SELECT:
            self._reset_character_scroll()
            self._char_pending_confirm = None

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
        if choice.fail_rate > self.config.max_training_fail_rate:
            return float("-inf")
        if choice.fail_rate <= 5:
            fail_penalty = 0
        elif choice.fail_rate <= 15:
            fail_penalty = choice.fail_rate * 1.5
        else:
            fail_penalty = choice.fail_rate * 3

        profile = state.build_profile if state else "balanced"
        strategic_bias = self.config.training_bias_by_profile.get(profile, {}).get(choice.name, 0)
        return choice.stat_gain + self.config.ring_bonus.get(choice.ring, 0) - fail_penalty + strategic_bias

    def _reset_character_scroll(self) -> None:
        self._char_scroll_count = 0
        self._char_scroll_down = True
        self._char_reversed = False
        self._char_seen_names = None

    def decide_character_select(self, selection: CharacterSelect, state: GameState) -> Action:
        if state.desired_character:
            # Two passes: prefer an exact name match, then fall back to a tolerant
            # substring match so noisy OCR (rank prefixes, middle dots, costume
            # prefixes) still resolves the right character.
            match = next(
                (opt for opt in selection.options if opt.name == state.desired_character),
                None,
            ) or next(
                (opt for opt in selection.options if _character_name_matches(opt.name, state.desired_character)),
                None,
            )
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
        attribute = state.desired_blessing_attribute or self.config.blessing_attribute_by_profile.get(state.build_profile, "power")
        matching = [option for option in choice.options if option.attribute == attribute and option.value is not None]
        if not matching:
            return Action("pause", None, f"no {attribute} blessing option with recognized value")

        best = max(matching, key=self.blessing_score)
        if choice.selected_name == best.name and choice.confirm_button is not None:
            return Action(
                "click",
                choice.confirm_button,
                f"confirm selected {attribute} blessing: {best.name}={best.value}, sub_blessings={best.sub_blessing_count}",
            )
        if best.value == self.config.max_blessing_value:
            return Action(
                "click",
                best.target,
                f"choose max {attribute} blessing: {best.name}={best.value}, sub_blessings={best.sub_blessing_count}",
            )
        return Action(
            "click",
            best.target,
            f"choose best {attribute} blessing: {best.name}={best.value}, sub_blessings={best.sub_blessing_count}",
        )

    def blessing_score(self, option: BlessingOption) -> tuple[int, int, str]:
        value = option.value if option.value is not None else -1
        return (value, option.sub_blessing_count, -option.target.y, -option.target.x, option.name)

    def decide_journey_start(self, journey: JourneyStart) -> Action:
        return Action("click", journey.start_button, "arcana is fixed, click journey start")

    def decide_confirm_dialog(self, dialog: ConfirmDialog) -> Action:
        return Action("click", dialog.confirm_button, f"confirm dialog: {dialog.title}")

    def decide_event_fast_forward_setting(self, setting: EventFastForwardSetting) -> Action:
        if setting.selected_mode == "all_events":
            return Action("click", setting.confirm_button, "confirm fast-forward all events")
        return Action("click", setting.all_events_option, "select fast-forward all events")

    def decide_dialogue(self, dialogue: DialogueScene) -> Action:
        return Action("click", dialogue.skip_button, f"dialogue {dialogue.variant}, click skip")

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

    def decide_relic_choice(self, choice: RelicChoice) -> Action:
        if choice.selected_name and choice.confirm_button is not None:
            return Action("click", choice.confirm_button, f"confirm selected relic {choice.selected_name}")

        if choice.fixed_name:
            for option in choice.options:
                if option.name == choice.fixed_name:
                    return Action("click", option.target, f"choose fixed relic {option.name}")
            return Action("pause", None, f"fixed relic not visible: {choice.fixed_name}")

        return self.decide_relic(choice.options)

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

        # If any commission is flagged suitable (red), honor that first; otherwise
        # take the lowest-tier (first) entry.
        suitable = [option for option in choice.options if option.has_red_text]
        best = suitable[0] if suitable else choice.options[0]
        if self._pending_commission == best.target and choice.accept_button is not None:
            self._pending_commission = None
            return Action("click", choice.accept_button, f"accept commission: {best.name}")
        self._pending_commission = best.target
        return Action("click", best.target, f"select commission: {best.name}")

    def decide_shop(self, items: Iterable[ShopItem]) -> Action:
        for item in items:
            key = self.config.shop_aliases.get(item.name, item.name)
            max_price = self.config.shop_whitelist.get(key)
            if max_price is not None and item.price <= max_price:
                return Action("click", item.target, f"buy whitelisted item {key} for {item.price}")
        return Action("skip", None, "skip shop: no whitelisted item at acceptable price")

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
