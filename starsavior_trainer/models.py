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
    # "获得奖励" reward-obtained popup (a fixed relic is granted, no choice). The
    # centre card is a dead click zone; only the "点击以继续" prompt advances it.
    REWARD = "reward"
    # 赛前流程(docs/prejourney-flow.md): 游戏主界面(左侧 战斗/管理/总部/公会/商店/观测
    # 竖排菜单), 右上角菜单按钮可能带红色感叹号也可能不带, 两种都从这里点开菜单栏。
    MAIN_SCREEN = "main_screen"
    # 主界面菜单栏面板(付费商店/主线商店/作战/旅程…图标网格)。注意与 GAME_MENU
    # (局内误触的 菜单+观测 弹窗)是两个不同画面。
    MAIN_MENU_PANEL = "main_menu_panel"
    # 通用「筛选」弹窗(职业行/能力值祝福属性行/救援者区段 + 重置/确认, 可滚动)。
    # 同一个 UI 组件出现在两处: 角色选择点漏斗(选职业, docx: 战士=UI「突击者」),
    # 刻印操作点属性筛选(选 力量/体力/韧性 等)。decide 按赛前进度决定点什么。
    FILTER_DIALOG = "filter_dialog"
    # 支援卡选择界面(好友卡入口): 左上「可借用」标签 + 好友按钮。没有「可借用」
    # 三个字时无法接好友卡, 直接点左上 < 退出(docx 6.1)。标题与旅程起点共用。
    SUPPORT_PICKER = "support_picker"
    # 好友支援卡墙(顶部「可借用次数: N/N」), OCR 卡名牌找配置的好友名。
    SUPPORT_FRIEND_LIST = "support_friend_list"
    # 支援卡详情(旅程效果/专属效果 标签列 + 右下蓝色「选择」)。
    SUPPORT_CARD_DETAIL = "support_card_detail"
    # 「达成目标列表」全屏黑底展示页(星光引导者 + 打勾目标列表 + 底部
    # 点击以继续)。评鉴战/远征达成后出现; 黑屏让所有常规锚都读不出字,
    # 不识别它就 unknown 死循环(2026-06-12 实跑卡死点)。
    GOAL_LIST = "goal_list"
    # 「跳过战斗」二次确认弹窗(确定要跳过评鉴战战斗吗? + 跳过战斗 蓝键)。
    # 远征评鉴战的这个弹窗布局与基础评鉴战不同, 老 battle 锚读不到, 蓝键
    # fallback 又把它误判成快转设置 → 解析不出选项 pause 死循环(实跑卡死点2)。
    SKIP_BATTLE_CONFIRM = "skip_battle_confirm"
    # 评鉴战结算页(FAIL/胜利: 很可惜,落败了… + 重新挑战/确认)。落败时点确认
    # 接受继续(不重打); 误判成训练大厅点空白会无限循环(实跑卡死点9)。
    BATTLE_RESULT = "battle_result"
    # 终局大厅: 右侧只剩「旅程结束」按钮(可习得潜质)。点它进终局结算/学技能。
    JOURNEY_END = "journey_end"
    # 终局「获得全新祝福」结算页(旅程成果已化为祝福 + 确认)。点确认收下。
    NEW_BLESSING = "new_blessing"
    # 「最终旅程结果」页(评级+总分+目标清单 + 重新观测/确认)。整局最后一关。
    FINAL_RESULT = "final_result"
    # The in-game 菜单 popup (指南/选项/编制信息/观测信息/重新观测/储存后前往大厅 +
    # an ✕ close). Reached by an accidental mis-click on the top-right menu button.
    # Dangerous to leave: its centre holds 重新观测/观测结束, which would restart or
    # end the run if clicked — so we must recognise it and click ✕ to close, never
    # the generic "click centre to advance" fallback.
    GAME_MENU = "game_menu"
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
    # Number of times to repeat a click in one execution. >1 turns a single
    # click into a rapid burst — used for "tap to continue / skip" advance
    # screens (reward popup, dialogue, post-training) so they're blown through
    # quickly instead of one click per loop iteration.
    repeat: int = 1


@dataclass(frozen=True)
class TrainingChoice:
    name: str
    stat_gain: int
    ring: str
    # 失败率(百分数)。None = 该卡未被选中,屏幕没显示它的失败率 → 未知(不是0%)。
    # 只有当前选中的卡会显示失败率;策略层把 None 当作"不可冒险"(见 training_score)。
    fail_rate: int | None
    target: Rect
    # internal 属性键(power/stamina/guts/wisdom/speed), 来自卡位循环, 永远可靠
    # (name 可能被 OCR 中文名覆盖)。
    attr: str = ""
    # 该训练上的支援卡人头数。人头列是**选中卡**共享固定位(实机确认), 所以
    # 只有选中帧能读到: -1 = 未知(没选中过), ≥0 = 选中时读到的真实数。
    # 前期策略轮询候选逐个选中读数比较(跟人头刷好感, 2026-06-12 用户拍板)。
    icon_count: int = -1
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
    # 住处 (30-coin lodging) option and the bottom-right 休息 confirm button.
    # Rest is a two-step flow (select option, then confirm) like training/commission.
    lodging: Rect | None = None
    confirm_button: Rect | None = None


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
    # 部位映射出的战斗属性(attack/crit_rate/crit_dmg/hp/defense/hit/resist/speed),
    # 与是否"队员全体"(组合圣遗物)。组合圣遗物按属性+build优先级选,普通按 score。
    attribute: str | None = None
    is_team: bool = False


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
    # 当前选中委托的「建议综合等级」(详情区数字, 如 RANK 17)。列表项只有阶名(低/中/
    # 高阶委托), 建议等级只在选中后于中央详情区显示 → 检视器逐个点开读它来选阶。
    selected_suggested_rank: int | None = None
    # 角色综合等级(委托界面左上 "RANK 21")。选"建议等级≤它的最高阶"委托用; 直接从本
    # 界面读, 不依赖先经过训练大厅。
    character_rank: int | None = None


@dataclass(frozen=True)
class ShopItem:
    name: str
    price: int
    target: Rect
    # 效果说明文本(商品名与效果无关,买/不买看效果). 需逐个点开商品读取。
    effect: str = ""


@dataclass(frozen=True)
class ShopScene:
    """Journey Trading (交易) screen state.

    The right-side list (``items``) gives each row's click target; effects only
    show in the centre detail once an item is selected, so ``selected_effect`` is
    the *currently-selected* item's effect text for this frame. The shop inspector
    clicks each row in turn, attributing each frame's ``selected_effect`` to the
    row it clicked last, then buys by effect (回体力 / 潜质点退还) via ``buy_button``
    or leaves via ``back_button``.
    """

    items: tuple[ShopItem, ...] = ()
    selected_effect: str = ""
    buy_button: Rect | None = None
    back_button: Rect | None = None


@dataclass(frozen=True)
class CharacterOption:
    name: str
    rank: str | None
    stars: int | None
    specialty: str | None
    selected: bool
    target: Rect
    # 形态/系列标记(每行职业图标下方文字): ""=普通, "ANOTHER"=第二形态, "COSMIC"=系列。
    # 游戏更新后同名角色有多形态, 用它 + 名字一起锁定目标形态。
    variant: str = ""


@dataclass(frozen=True)
class CharacterSelect:
    options: list[CharacterOption]
    confirm_button: Rect
    selected_name: str | None = None
    can_scroll: bool = True
    # 右上角「排序」旁的漏斗筛选按钮(赛前职业筛选入口); 区域未配置时为 None。
    filter_button: Rect | None = None


@dataclass(frozen=True)
class FilterDialog:
    """筛选弹窗 payload(角色选择的职业筛选; 按钮位置由 OCR bbox 定位)。

    职业按钮 UI 用语: 坦克/突击者/游侠/术师/刺客/辅助。
    刻印环节不再使用本弹窗(2026-06-12 改为星标过滤+旧逻辑选取)。
    """

    profession_buttons: dict[str, Rect]
    confirm_button: Rect
    reset_button: Rect | None = None


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
    # 顶部星标(收藏过滤)按钮: 点亮后自动过滤出「祝福」, 之后用旧「按属性挑
    # 数值最高」逻辑选取(2026-06-12 用户拍板的简化流程, 取代弹窗属性筛选)。
    star_filter_button: Rect | None = None
    # 星标当前是否点亮(像素检测: 亮=白底高亮按钮, 暗=未激活)。toggle 按钮
    # 不能盲点 —— 游戏跨界面记住状态, 槽2 进来已亮时再点反而会关掉过滤。
    star_filter_active: bool = False


@dataclass(frozen=True)
class JourneyStart:
    start_button: Rect
    auto_journey_button: Rect | None = None
    arcana_slots: list[Rect] | None = None
    # ---- 赛前流程(卡组切换+好友卡)新增, 全部可缺省 ----
    # 5 个卡组指示圆点中当前亮的是第几个(1-5); 检测不出/区域未配置 → None。
    current_deck: int | None = None
    previous_button: Rect | None = None
    next_button: Rect | None = None


@dataclass(frozen=True)
class SupportPicker:
    """支援卡选择界面: 「可借用」存在才可接好友卡, 否则点返回退出。"""

    back_button: Rect
    friend_button: Rect | None = None
    has_borrow: bool = False


@dataclass(frozen=True)
class SupportFriendCard:
    name: str
    target: Rect


@dataclass(frozen=True)
class SupportFriendList:
    """好友支援卡墙: 名牌 OCR + 卡中心点击位(第一排, 好友通常置顶)。"""

    cards: list[SupportFriendCard]
    back_button: Rect | None = None


@dataclass(frozen=True)
class SupportCardDetail:
    select_button: Rect


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
    # D-DAY 评鉴战日大厅: 这俩按钮取代平时的 训练/委托/休息(评鉴战上、交易下)。
    rating_battle_button: Rect | None = None
    trading_button: Rect | None = None
    has_commission_alert: bool = False
    has_shop_alert: bool = False
    can_learn_skill: bool = False


@dataclass(frozen=True)
class MainScreen:
    """游戏主界面 payload: 右上角菜单按钮(进旅途流程的入口)。"""

    menu_button: Rect


@dataclass(frozen=True)
class MainMenuPanel:
    """主界面菜单栏 payload: 「旅程」入口按钮。"""

    journey_entry: Rect


@dataclass(frozen=True)
class GameState:
    current_rank: str = "C"
    coins: int = 0
    safe_mode: bool = True
    desired_character: str | None = None
    # 目标角色的形态(""=普通, "ANOTHER"/"COSMIC"等)。同名多形态时用它锁定正确那个。
    desired_variant: str = ""
    build_profile: str = "balanced"
    desired_blessing_attribute: str | None = None
    # Current journey round/turn (1-based). None when unknown/not yet read from the
    # hub. Drives the early-game training bias (see PolicyConfig.early_game_rounds).
    current_round: int | None = None
    # 角色综合等级(数字, 从训练大厅 "RANK 21" 读)。委托选阶用: 选建议综合等级≤它的最高阶
    # 委托(能做的最高阶)。None=未知时退回选最低阶。
    character_rank: int | None = None
    # Skills are intentionally skipped mid-run. Enable only when the journey-end
    # flow enters the final skill-learning phase.
    allow_skill_learning: bool = False
    # 赛前流程配置(难度/职业/刻印序号/卡组/好友卡, 见 run_config.PreJourneyConfig)。
    # None = 老调用方式, 赛前增强逻辑全部跳过, 行为与之前完全一致。
    # 类型用 object 以避免 models→run_config 的依赖边; 实际类型是 PreJourneyConfig。
    prejourney: object | None = None


@dataclass(frozen=True)
class Observation:
    screen: Screen
    confidence: float
    payload: object | None = None
    source: str | None = None
