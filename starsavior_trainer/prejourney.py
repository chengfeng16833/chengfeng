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
    CharacterFilter,
    CharacterSelect,
    GameState,
    MainMenuPanel,
    MainScreen,
    Observation,
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

#: 刻印筛选后的网格每排卡数(docx: 第4个=第1排第4个, 第12个=第3排第2个 → 每排5)。
IMPRINT_GRID_COLUMNS = 5

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


def imprint_index_to_row_col(index: int) -> tuple[int, int]:
    """1 起算的刻印序号 → (排, 列), 每排 5 个; 非法序号回落第 1 个(安全默认)。"""
    if index < 1:
        return (1, 1)
    return ((index - 1) // IMPRINT_GRID_COLUMNS + 1, (index - 1) % IMPRINT_GRID_COLUMNS + 1)


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


def decide_character_filter(
    obs: Observation, state: GameState, policy: "TrainerPolicy"
) -> Action:
    """筛选弹窗: 第一帧点配置职业, 第二帧点确认(两步, 防 OCR 抖动横跳)。"""
    if not isinstance(obs.payload, CharacterFilter):
        return Action("pause", None, "character filter missing payload")
    pre = state.prejourney
    profession = normalize_profession(getattr(pre, "profession", "") if pre else "")
    if not profession:
        # 没配职业却进了筛选窗(误触/手点) → 直接确认关闭, 不乱选。
        return Action("click", obs.payload.confirm_button, "no profession configured, close filter")
    progress = progress_of(policy)
    if progress.extra.get("profession_clicked"):
        progress.extra.pop("profession_clicked", None)
        progress.profession_filter_done = True
        return Action("click", obs.payload.confirm_button, f"confirm profession filter {profession}")
    button = obs.payload.profession_buttons.get(profession)
    if button is None:
        return Action("pause", None, f"profession button {profession} not found in filter dialog")
    progress.extra["profession_clicked"] = True
    return Action("click", button, f"select profession filter {profession}")


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
