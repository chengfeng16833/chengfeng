from __future__ import annotations

from dataclasses import dataclass, field, replace

from starsavior_trainer.models import Action, ShopScene


@dataclass
class ShopInspector:
    """Buy Journey Trading (交易) items by their effect, reading each one first.

    On the trading screen a product's effect only shows in the centre detail panel
    once that product is *selected* — the right-side list rows just show a name +
    price (which OCR unreliably). So, like the training/blessing inspectors, we
    CLICK each row in turn; the next frame's centre detail (``scene.selected_effect``)
    is that row's effect, which we attribute to the row we clicked last. Once every
    row's effect is known we buy the first worth-buying item (回体力 / 潜质点退还,
    per ``policy.shop_item_worth_buying``) with a two-step select→购买, then re-inspect
    to catch a second worthy item; when nothing (more) is worth buying we leave via
    the top-left back arrow and mark D-DAY trading done so the hub goes to 评鉴战.

    Rows are tracked by 1-based index (positions are stable within a visit and far
    more reliable than the flaky name OCR). ``bought_effects`` guards against
    re-buying the same item if it lingers in the list after purchase.

    NOTE (needs live confirmation): what the screen does right after 购买 — whether
    the bought row disappears, greys out, or a confirm popup appears (which would
    bounce us off SHOP and reset this inspector) — is not yet observed. If a popup
    resets us and the item lingers, bought-tracking may need to move onto the policy
    (persist across screens within a D-DAY).
    """

    effects: dict[int, str] = field(default_factory=dict)  # 1-based row index -> effect text
    pending_index: int | None = None  # row clicked to inspect, awaiting its detail next frame
    last_selected_index: int | None = None  # row currently selected on screen
    bought_effects: set[str] = field(default_factory=set)

    def decide(self, scene: ShopScene, policy) -> Action | None:
        items = list(scene.items)
        if not items:
            return None  # let the policy pause — nothing to act on
        n = len(items)

        # 1) Record the effect of the row we clicked last turn: clicking it selected
        #    it, so the centre detail now shows ITS effect.
        if self.pending_index is not None and scene.selected_effect.strip():
            self.effects[self.pending_index] = scene.selected_effect.strip()
            self.last_selected_index = self.pending_index
            self.pending_index = None

        # 2) Inspect any not-yet-seen row by clicking it (selects it -> detail shows
        #    its effect next frame).
        for idx in range(1, n + 1):
            if idx not in self.effects:
                self.pending_index = idx
                return Action("click", items[idx - 1].target, f"inspect shop item #{idx}")

        # 3) All inspected. Buy the first worth-buying, not-yet-bought item via a
        #    two-step select→购买 (mirrors the training inspector's select→confirm).
        for idx in range(1, n + 1):
            effect = self.effects.get(idx, "")
            if effect in self.bought_effects:
                continue
            if not policy.shop_item_worth_buying(replace(items[idx - 1], effect=effect)):
                continue
            if self.last_selected_index == idx and scene.buy_button is not None:
                self.bought_effects.add(effect)
                # The list changes after a purchase, so re-inspect from scratch
                # (bought_effects still guards against re-buying this one).
                self.effects = {}
                self.last_selected_index = None
                self.pending_index = None
                return Action("click", scene.buy_button, f"购买 shop item #{idx}: {effect}")
            self.last_selected_index = idx
            self.pending_index = None
            return Action("click", items[idx - 1].target, f"select shop item #{idx} to buy: {effect}")

        # 4) Nothing (more) worth buying — leave trading.
        policy._dday_trading_done = True
        self.reset()
        if scene.back_button is not None:
            return Action("click", scene.back_button, "交易: 没有想买的(回体力/潜质点退还), 退出")
        return Action("skip", None, "交易: 没有想买的, 无返回按钮")

    def reset(self) -> None:
        self.effects = {}
        self.pending_index = None
        self.last_selected_index = None
        self.bought_effects = set()
