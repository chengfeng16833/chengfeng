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
    Rect,
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


def decide_filter_dialog(
    obs: Observation, state: GameState, policy: "TrainerPolicy"
) -> Action:
    """通用「筛选」弹窗: 按赛前进度决定点职业(角色选择)还是点属性(刻印)。

    两步式: 第一帧点目标按钮, 第二帧点确认(防 OCR 抖动横跳)。
    没有任何待办筛选时(误触/手点开的)直接确认关闭, 不乱选。
    """
    if not isinstance(obs.payload, FilterDialog):
        return Action("pause", None, "filter dialog missing payload")
    payload = obs.payload
    pre = state.prejourney
    progress = progress_of(policy)

    # 刻印属性筛选阶段(由 BLESSING_CHOICE 钩子点开属性筛选后进入)。
    if progress.extra.get("imprint_stage") == "attr_dialog":
        attribute = _imprint_attribute(pre)
        if progress.extra.get("attr_clicked"):
            progress.extra.pop("attr_clicked", None)
            progress.extra["imprint_stage"] = "filtered"
            return Action("click", payload.confirm_button, f"confirm imprint attribute filter {attribute}")
        button = (payload.attribute_buttons or {}).get(attribute)
        if button is None:
            return Action("pause", None, f"attribute button {attribute} not found in filter dialog")
        progress.extra["attr_clicked"] = True
        return Action("click", button, f"select imprint attribute filter {attribute}")

    # 角色选择的职业筛选阶段。
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


def _imprint_attribute(pre: object | None) -> str:
    """刻印属性: 职业→属性映射(辅助/坦克→体力, 艾黛→韧性, 其余→力量)。

    优先用 PreJourneyConfig.imprint_attribute()(源头实现), 拿不到时回退力量。
    """
    method = getattr(pre, "imprint_attribute", None)
    if callable(method):
        return method()
    return "力量"


def decide_blessing_choice_imprint(
    choice: BlessingChoice, state: GameState, policy: "TrainerPolicy"
) -> Action | None:
    """刻印操作界面的赛前筛选流程钩子(docs/prejourney-flow.md 5.1)。

    返回 None = 不适用(无赛前配置/区域缺失), 调用方走旧「选最高值祝福」逻辑。
    流程: 点数值筛选 → 下拉选「能力值领域」 → 点属性筛选 → (FILTER_DIALOG 处理
    属性弹窗) → 筛选完按配置序号点卡 → 确认。
    """
    pre = state.prejourney
    if pre is None:
        return None
    progress = progress_of(policy)
    stage = progress.extra.get("imprint_stage")

    # 下拉展开时优先处理(OCR 实际看到「能力值领域」项, 比 stage 记忆更可信)。
    if choice.value_dropdown_ability_item is not None:
        progress.extra["imprint_stage"] = "value_filtered"
        return Action(
            "click", choice.value_dropdown_ability_item, "imprint: choose 能力值领域 in value dropdown"
        )

    if stage is None:
        if choice.value_filter_button is None:
            return None  # 区域未配置, 不挡旧逻辑。
        progress.extra["imprint_stage"] = "value_dropdown"
        return Action("click", choice.value_filter_button, "imprint: open value filter dropdown")

    if stage == "value_dropdown":
        # 点过数值筛选但这帧没读到下拉(OCR 抖动/动画) → 再点一次入口。
        if choice.value_filter_button is not None:
            return Action("click", choice.value_filter_button, "imprint: reopen value filter dropdown")
        return Action("pause", None, "imprint: value dropdown not visible")

    if stage == "value_filtered":
        if choice.attr_filter_button is None:
            return Action("pause", None, "imprint: attr filter button region missing")
        progress.extra["imprint_stage"] = "attr_dialog"
        return Action("click", choice.attr_filter_button, "imprint: open attribute filter dialog")

    if stage == "attr_dialog":
        # 属性弹窗应被分类成 FILTER_DIALOG; 走到这里说明弹窗没认出来, 再点一次。
        if choice.attr_filter_button is not None:
            return Action("click", choice.attr_filter_button, "imprint: reopen attribute filter dialog")
        return Action("pause", None, "imprint: attribute dialog not recognised")

    if stage == "filtered":
        slot = int(progress.extra.get("current_imprint_slot", 1))
        index = int(getattr(pre, "imprint_slot_2_index", 1) if slot == 2 else getattr(pre, "imprint_slot_1_index", 1))
        row, col = imprint_index_to_row_col(index)
        cell = _grid_cell(choice, row, col)
        if cell is None:
            return Action("pause", None, "imprint: grid origin region missing")
        progress.extra["imprint_stage"] = "card_clicked"
        return Action("click", cell, f"imprint slot {slot}: pick card #{index} (row {row} col {col})")

    if stage == "card_clicked":
        if choice.confirm_button is None:
            return Action("pause", None, "imprint: confirm button missing after card click")
        progress.extra.pop("imprint_stage", None)
        return Action("click", choice.confirm_button, "imprint: confirm chosen card")

    return None


def _grid_cell(choice: BlessingChoice, row: int, col: int) -> Rect | None:
    if choice.grid_origin is None:
        return None
    origin = choice.grid_origin
    return Rect(
        origin.x + (col - 1) * choice.grid_step_x,
        origin.y + (row - 1) * choice.grid_step_y,
        origin.width,
        origin.height,
    )


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
