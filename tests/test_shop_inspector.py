import unittest

from starsavior_trainer.models import Rect, ShopItem, ShopScene
from starsavior_trainer.policy import TrainerPolicy
from starsavior_trainer.shop_inspector import ShopInspector

_R1 = Rect(2240, 552, 260, 62)
_R2 = Rect(2240, 707, 260, 62)
_R3 = Rect(2240, 862, 260, 62)
_BUY = Rect(2070, 1245, 360, 90)
_BACK = Rect(75, 55, 95, 95)


def _scene(selected_effect: str = "") -> ShopScene:
    """Journey Trading with 3 rows; the centre detail shows `selected_effect`,
    i.e. the effect of whichever row is currently selected this frame. Names/prices
    OCR unreliably on the real screen, so they're left blank — the inspector tracks
    rows by index and decides by effect."""
    items = (ShopItem("", 0, _R1), ShopItem("", 0, _R2), ShopItem("", 0, _R3))
    return ShopScene(items=items, selected_effect=selected_effect, buy_button=_BUY, back_button=_BACK)


class ShopInspectorTest(unittest.TestCase):
    def test_inspects_each_row_then_buys_worthy_last_inspected(self) -> None:
        insp = ShopInspector()
        policy = TrainerPolicy()

        a = insp.decide(_scene(), policy)  # nothing recorded yet -> click row1 to read its effect
        self.assertEqual(a.kind, "click")
        self.assertEqual(a.target, _R1)

        a = insp.decide(_scene("攻击力+5%"), policy)  # row1 = 攻击(not worthy) -> inspect row2
        self.assertEqual(a.target, _R2)

        a = insp.decide(_scene("攻击力+3%"), policy)  # row2 = 攻击 -> inspect row3
        self.assertEqual(a.target, _R3)

        # row3 = 潜质点退还 (worthy). It was the last row clicked -> already selected -> 购买.
        a = insp.decide(_scene("每回合伤害+1%。潜质点数8退还"), policy)
        self.assertEqual(a.kind, "click")
        self.assertEqual(a.target, _BUY)

    def test_reselects_worthy_item_when_not_last_inspected(self) -> None:
        insp = ShopInspector()
        policy = TrainerPolicy()

        insp.decide(_scene(), policy)  # inspect row1
        insp.decide(_scene("首次战斗开始时回复体力10"), policy)  # row1 worthy(回体力) -> inspect row2
        insp.decide(_scene("攻击力+5%"), policy)  # row2 -> inspect row3
        a = insp.decide(_scene("防御力+5%"), policy)  # row3 not worthy; best worthy = row1 -> select row1
        self.assertEqual(a.target, _R1)

        a = insp.decide(_scene("首次战斗开始时回复体力10"), policy)  # row1 now selected -> 购买
        self.assertEqual(a.target, _BUY)

    def test_exits_via_back_when_nothing_worth_buying(self) -> None:
        insp = ShopInspector()
        policy = TrainerPolicy()

        insp.decide(_scene(), policy)
        insp.decide(_scene("攻击力+5%"), policy)
        insp.decide(_scene("防御力+5%"), policy)
        a = insp.decide(_scene("效果命中+5%"), policy)  # all inspected, none worthy -> exit
        self.assertEqual(a.kind, "click")
        self.assertEqual(a.target, _BACK)
        self.assertTrue(policy._dday_trading_done)

    def test_does_not_rebuy_same_effect_after_purchase(self) -> None:
        insp = ShopInspector()
        policy = TrainerPolicy()

        insp.decide(_scene(), policy)
        insp.decide(_scene("攻击力+5%"), policy)
        insp.decide(_scene("攻击力+3%"), policy)
        buy = insp.decide(_scene("潜质点数8退还"), policy)  # buy row3
        self.assertEqual(buy.target, _BUY)

        # After the purchase the bot re-inspects. Suppose the bought item is still
        # listed (or its effect re-read): it must NOT be bought again — eventually
        # the inspector exits instead of looping on 购买.
        insp.decide(_scene(), policy)
        insp.decide(_scene("攻击力+5%"), policy)
        insp.decide(_scene("攻击力+3%"), policy)
        after = insp.decide(_scene("潜质点数8退还"), policy)
        self.assertEqual(after.kind, "click")
        self.assertEqual(after.target, _BACK)


if __name__ == "__main__":
    unittest.main()
