# -*- coding: utf-8 -*-
"""赛前流程(主界面→进旅途)的决策助手 — 迁移计划 Phase 2。

流程知识: docs/prejourney-flow.md(整理自用户 docx, 19 张截图)。
本模块收纳赛前各画面的换算与决策逻辑, screens/ 注册表委托到这里,
避免 policy.py 继续膨胀(物理搬迁方向的第一个落点)。

依赖方向: prejourney → models/run_config; 不 import policy(decide 函数的
policy 参数 duck-typed, 与 screens/__init__.py 的委托函数一致)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from starsavior_trainer.models import (
    Action,
    BlessingChoice,
    CharacterSelect,
    FilterDialog,
    GameState,
    MainMenuPanel,
    MainScreen,
    Observation,
    SupportCardDetail,
    SupportFriendList,
    SupportPicker,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型标注
    from starsavior_trainer.policy import TrainerPolicy


# ---------------------------------------------------------------------------
# 配置换算
# ---------------------------------------------------------------------------

# 难度文本归一化: GUI/CLI 可能传中文(docx 用语)或英文 key。
_DIFFICULTY_ALIASES = {
    "easy": "easy",
    "简单": "easy",
    "normal": "normal",
    "一般": "normal",
    "hard": "hard",
    "困难": "hard",
}

# 职业用语归一化: docx 正文写「战士/术士」, 游戏筛选弹窗 UI 实际是
# 坦克/突击者/游侠/术师/刺客/辅助(见 screenshots/prejourney/image5)。
_PROFESSION_ALIASES = {
    "坦克": "坦克",
    "突击者": "突击者",
    "战士": "突击者",
    "游侠": "游侠",
    "术师": "术师",
    "术士": "术师",
    "刺客": "刺客",
    "辅助": "辅助",
}


def normalize_difficulty(value: str) -> str:
    """难度文本 → easy/normal/hard; 空、default、不认识的文本 → default(不点难度)。"""
    return _DIFFICULTY_ALIASES.get((value or "").strip(), "default")


def normalize_profession(value: str) -> str:
    """职业文本 → 游戏 UI 用语; 空或不认识 → ""(不筛选)。"""
    return _PROFESSION_ALIASES.get((value or "").strip(), "")


# ---------------------------------------------------------------------------
# 单局赛前进度(policy 实例上的瞬时状态, 与 _pending_blessing 等同类)
# ---------------------------------------------------------------------------


@dataclass
class PrejourneyProgress:
    """一局内赛前流程已完成的步骤标记(防止重复点击/死循环)。"""

    difficulty_clicked: bool = False
    profession_filter_done: bool = False
    friend_card_done: bool = False
    # 刻印流程状态见后续切片(value_filtered / attr_filtered / current_slot)。
    extra: dict = field(default_factory=dict)

    def reset(self) -> None:
        self.difficulty_clicked = False
        self.profession_filter_done = False
        self.friend_card_done = False
        self.extra.clear()


def progress_of(policy: "TrainerPolicy") -> PrejourneyProgress:
    """取 policy 上的赛前进度, 没有则惰性创建(老构造路径也能用)。"""
    progress = getattr(policy, "prejourney_progress", None)
    if progress is None:
        progress = PrejourneyProgress()
        policy.prejourney_progress = progress
    return progress


# ---------------------------------------------------------------------------
# 画面决策
# ---------------------------------------------------------------------------


def decide_main_screen(obs: Observation, state: GameState, policy: "TrainerPolicy") -> Action:
    """游戏主界面: 点右上菜单按钮(有无红色感叹号都一样)。"""
    if not isinstance(obs.payload, MainScreen):
        return Action("pause", None, "main screen missing menu button observation")
    return Action("click", obs.payload.menu_button, "main screen, open menu panel")


def decide_main_menu_panel(obs: Observation, state: GameState, policy: "TrainerPolicy") -> Action:
    """主界面菜单栏: 点「旅程」入口。"""
    if not isinstance(obs.payload, MainMenuPanel):
        return Action("pause", None, "main menu panel missing journey entry observation")
    return Action("click", obs.payload.journey_entry, "main menu panel, enter journey")


def maybe_open_profession_filter(
    selection: CharacterSelect, state: GameState, policy: "TrainerPolicy"
) -> Action | None:
    """角色选择画面的前置钩子: 配置了职业且还没筛选 → 点漏斗按钮弹筛选窗。

    返回 None 表示不需要筛选, 调用方继续走现有找角色逻辑。
    """
    pre = state.prejourney
    if pre is None:
        return None
    profession = normalize_profession(getattr(pre, "profession", ""))
    if not profession:
        return None
    progress = progress_of(policy)
    if progress.profession_filter_done:
        return None
    if selection.filter_button is None:
        # 区域没配置时不挡现有流程(找角色照旧, 只是少了筛选)。
        return None
    return Action("click", selection.filter_button, f"open profession filter for {profession}")


def decide_filter_dialog(
    obs: Observation, state: GameState, policy: "TrainerPolicy"
) -> Action:
    """「筛选」弹窗: 角色选择的职业筛选。

    两步式: 第一帧点职业按钮(OCR 定位), 第二帧点确认(防 OCR 抖动横跳)。
    没有待办筛选时(误触/手点开/记忆丢失)直接确认关闭, 不乱选 —— 关掉后
    底层画面会按需要重新打开并重走流程, 天然自愈。
    """
    if not isinstance(obs.payload, FilterDialog):
        return Action("pause", None, "filter dialog missing payload")
    payload = obs.payload
    pre = state.prejourney
    progress = progress_of(policy)

    profession = normalize_profession(getattr(pre, "profession", "") if pre else "")
    if profession and not progress.profession_filter_done:
        if progress.extra.get("profession_clicked"):
            progress.extra.pop("profession_clicked", None)
            progress.profession_filter_done = True
            return Action("click", payload.confirm_button, f"confirm profession filter {profession}")
        button = payload.profession_buttons.get(profession)
        if button is None:
            return Action("pause", None, f"profession button {profession} not found in filter dialog")
        progress.extra["profession_clicked"] = True
        return Action("click", button, f"select profession filter {profession}")

    return Action("click", payload.confirm_button, "no pending filter step, close dialog")


def decide_blessing_choice_imprint(
    choice: BlessingChoice, state: GameState, policy: "TrainerPolicy"
) -> Action | None:
    """刻印操作界面: 星标没亮就点亮(过滤出祝福), 然后交回旧「选最高值」逻辑。

    2026-06-12 用户拍板的最终方案(取代弹窗属性筛选)。星标是 toggle 且游戏
    跨界面记住状态(槽1 开了, 槽2 进来还亮着) —— 所以不按"点过没点过"记忆,
    而按**画面上的点亮状态**决定: 暗→点亮; 亮→直接选卡。跨进程/换槽全免疫。
    返回 None = 星标已亮 / 区域未配置, 调用方继续旧选取逻辑。
    """
    if choice.star_filter_button is None:
        return None
    if not choice.star_filter_active:
        return Action("click", choice.star_filter_button, "imprint: star-filter to blessings")
    return None


# ---------------------------------------------------------------------------
# 支援卡相关画面(2026-06-12 拍板: 卡组/好友卡由用户人工配置, bot 不主动进入;
# 以下三画面的识别保留, 仅当误入时自愈退出)
# ---------------------------------------------------------------------------


def decide_support_picker(obs: Observation, state: GameState, policy: "TrainerPolicy") -> Action:
    """支援卡选择界面: 有「可借用」→ 点好友按钮; 没有 → 点返回退出(不能借)。"""
    if not isinstance(obs.payload, SupportPicker):
        return Action("pause", None, "support picker missing payload")
    payload = obs.payload
    progress = progress_of(policy)
    pre = state.prejourney
    friend = str(getattr(pre, "friend_support_name", "") or "").strip() if pre else ""
    if not friend or progress.friend_card_done:
        # 不该在这个界面(没配好友/已借完) → 返回退出, 自愈。
        return Action("click", payload.back_button, "support picker: nothing to do, back out")
    if payload.has_borrow and payload.friend_button is not None:
        return Action("click", payload.friend_button, "support picker: open friend card list")
    # 没有「可借用」= 本局借不了(次数用完/无好友), 跳过好友卡直接回去开跑。
    progress.friend_card_done = True
    return Action("click", payload.back_button, "support picker: borrow unavailable, skip friend card")


def decide_support_friend_list(
    obs: Observation, state: GameState, policy: "TrainerPolicy"
) -> Action:
    """好友支援卡墙: OCR 名牌找配置好友名(含即可), 点卡中心进详情。"""
    if not isinstance(obs.payload, SupportFriendList):
        return Action("pause", None, "support friend list missing payload")
    pre = state.prejourney
    friend = str(getattr(pre, "friend_support_name", "") or "").strip() if pre else ""
    payload = obs.payload
    if not friend:
        if payload.back_button is not None:
            return Action("click", payload.back_button, "friend list: no friend configured, back out")
        return Action("pause", None, "friend list: no friend configured")
    for card in payload.cards:
        if friend in card.name or card.name in friend:
            return Action("click", card.target, f"friend list: pick {card.name}")
    # 第一排没找到: 好友通常置顶, 找不到先 pause 留人工看(滚动逻辑待实机校准)。
    return Action("pause", None, f"friend list: {friend} not found in first row")


def decide_support_card_detail(
    obs: Observation, state: GameState, policy: "TrainerPolicy"
) -> Action:
    """支援卡详情: 点「选择」确认借卡, 标记好友卡完成。"""
    if not isinstance(obs.payload, SupportCardDetail):
        return Action("pause", None, "support card detail missing payload")
    progress = progress_of(policy)
    progress.friend_card_done = True
    return Action("click", obs.payload.select_button, "support card detail: confirm borrow")


def decide_initial_with_difficulty(
    obs: Observation, state: GameState, policy: "TrainerPolicy"
) -> Action:
    """「选择旅程」INITIAL 画面: 配置了难度则先点难度按钮, 再点开始。

    点已选中的难度无副作用, 所以不识别当前难度, 每局固定点一次(幂等)。
    无 prejourney 配置时与旧行为完全一致(直接点开始)。
    """
    pre = state.prejourney
    if pre is not None:
        difficulty = normalize_difficulty(pre.difficulty)
        progress = progress_of(policy)
        if difficulty != "default" and not progress.difficulty_clicked:
            button = policy.config.difficulty_buttons.get(difficulty)
            if button is not None:
                progress.difficulty_clicked = True
                return Action("click", button, f"select journey difficulty {difficulty}")
    return Action("click", policy.config.start_button, "initial screen, click start")
