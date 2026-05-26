from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Screen(str, Enum):
    INITIAL = "initial"
    CHARACTER_SELECT = "character_select"
    BLESSING_SETUP = "blessing_setup"
    BLESSING_CHOICE = "blessing_choice"
    JOURNEY_START = "journey_start"
    CONFIRM_DIALOG = "confirm_dialog"
    EVENT_FAST_FORWARD_SETTING = "event_fast_forward_setting"
    DIALOGUE = "dialogue"
    TRAINING_HUB = "training_hub"
    TRAINING_SELECT = "training_select"
    REST_SUBMENU = "rest_submenu"
    EVENT_CHOICE = "event_choice"
    RELIC_CHOICE = "relic_choice"
    COMMISSION_SELECT = "commission_select"
    SHOP = "shop"
    POST_TRAINING = "post_training"
    BATTLE = "battle"
    SKILL_SELECT = "skill_select"
    REGION_MOVE = "region_move"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True)
class Action:
    kind: str
    target: Rect | None
    reason: str
    confidence: float = 1.0
    scroll_clicks: int = 0


@dataclass(frozen=True)
class TrainingChoice:
    name: str
    stat_gain: int
    ring: str
    fail_rate: int
    target: Rect
    # Whether this card is currently highlighted/selected (only the selected card
    # shows its 失败率 on screen). The screen-level confirm (训练) button is carried
    # on each choice so the policy can confirm once the desired card is selected.
    selected: bool = False
    confirm_button: Rect | None = None
    # Top-left back arrow, used to leave TRAINING_SELECT back to the hub when every
    # training's fail rate is too high (so the hub-level decision can choose rest).
    back_button: Rect | None = None


@dataclass(frozen=True)
class RestSubmenu:
    coins: int
    has_meditation_room: bool
    meditation_room: Rect
    rough_sleep: Rect


@dataclass(frozen=True)
class EventOption:
    text: str
    target: Rect
    # The event's title (OCR'd from the screen), carried so the policy can look
    # the event up in config/events.json for its recommended option.
    event_title: str = ""


@dataclass(frozen=True)
class RelicOption:
    name: str
    score: int | None
    target: Rect


@dataclass(frozen=True)
class RelicChoice:
    options: list[RelicOption]
    confirm_button: Rect | None = None
    fixed_name: str | None = None
    selected_name: str | None = None


@dataclass(frozen=True)
class CommissionOption:
    name: str
    rank: str
    has_red_text: bool
    target: Rect


@dataclass(frozen=True)
class CommissionChoice:
    options: list[CommissionOption]
    accept_button: Rect | None = None
    # Top-left back arrow, used to leave the screen when no suitable commission
    # is available (rule: only accept red-text/suitable commissions, else exit).
    back_button: Rect | None = None


@dataclass(frozen=True)
class ShopItem:
    name: str
    price: int
    target: Rect


@dataclass(frozen=True)
class CharacterOption:
    name: str
    rank: str | None
    stars: int | None
    specialty: str | None
    selected: bool
    target: Rect


@dataclass(frozen=True)
class CharacterSelect:
    options: list[CharacterOption]
    confirm_button: Rect
    selected_name: str | None = None
    can_scroll: bool = True


@dataclass(frozen=True)
class BlessingSlot:
    index: int
    occupied: bool
    target: Rect


@dataclass(frozen=True)
class BlessingSetup:
    slots: list[BlessingSlot]
    auto_equip_button: Rect
    confirm_button: Rect
    can_confirm: bool


@dataclass(frozen=True)
class BlessingOption:
    name: str
    attribute: str
    value: int | None
    target: Rect
    sub_blessing_count: int = 0
    sub_blessing_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlessingChoice:
    options: list[BlessingOption]
    confirm_button: Rect | None = None
    selected_name: str | None = None
    detail_sub_blessing_count: int = 0


@dataclass(frozen=True)
class JourneyStart:
    start_button: Rect
    auto_journey_button: Rect | None = None
    arcana_slots: list[Rect] | None = None


@dataclass(frozen=True)
class ConfirmDialog:
    title: str
    message: str
    confirm_button: Rect
    cancel_button: Rect | None = None


@dataclass(frozen=True)
class EventFastForwardSetting:
    no_fast_forward_option: Rect
    watched_only_option: Rect
    all_events_option: Rect
    confirm_button: Rect
    selected_mode: str | None = None


@dataclass(frozen=True)
class DialogueScene:
    skip_button: Rect
    variant: str = "default"
    text_area: Rect | None = None


@dataclass(frozen=True)
class BattleScene:
    skip_button: Rect
    confirm_button: Rect | None = None
    confirm_active: bool = False


@dataclass(frozen=True)
class SkillOption:
    name: str
    effect: str | None = None
    cost: int | None = None
    target: Rect | None = None


@dataclass(frozen=True)
class TrainingHubStatus:
    turn_label: str | None = None
    coins: int | None = None
    rank_label: str | None = None
    potential_points: int | None = None
    training_button: Rect | None = None
    commission_button: Rect | None = None
    rest_button: Rect | None = None
    skill_button: Rect | None = None
    shop_button: Rect | None = None
    has_commission_alert: bool = False
    has_shop_alert: bool = False
    can_learn_skill: bool = False


@dataclass(frozen=True)
class GameState:
    current_rank: str = "C"
    coins: int = 0
    safe_mode: bool = True
    desired_character: str | None = None
    build_profile: str = "balanced"
    desired_blessing_attribute: str | None = None


@dataclass(frozen=True)
class Observation:
    screen: Screen
    confidence: float
    payload: object | None = None
    source: str | None = None
