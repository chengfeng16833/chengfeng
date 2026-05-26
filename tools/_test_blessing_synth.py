"""blessing_choice 解析逻辑验证（无需 OCR，无需截图）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from starsavior_trainer.regions import load_region_profile
from starsavior_trainer.screen_reader import parse_blessing_choice, RegionText
from starsavior_trainer.models import BlessingChoice, GameState
from starsavior_trainer.policy import TrainerPolicy

profile = load_region_profile("config/regions/2560x1440.json")
policy = TrainerPolicy()

def test1():
    """20卡全解析, 详情面板力量:35, 策略选card_02(力量45)"""
    texts = [RegionText("blessing_choice_anchor_archive", "\u661f\u8fb0\u6863\u6848", 0.95)]
    texts.append(RegionText("blessing_choice_detail_type", "\u529b\u91cf:35", 0.90))
    attrs = [
        ("\u529b\u91cf:35","\u529b\u91cf:45","\u4f53\u529b:40","\u529b\u91cf:30","\u97e7\u6027:38",
         "\u529b\u91cf:25","\u4e13\u6ce8:42","\u529b\u91cf:20","\u4f53\u529b:35","\u529b\u91cf:28",
         "\u4fdd\u62a4:32","\u529b\u91cf:15","\u4e13\u6ce8:36","\u4f53\u529b:28","\u529b\u91cf:22",
         "\u97e7\u6027:30","\u529b\u91cf:18","\u4e13\u6ce8:25","\u4f53\u529b:20","\u529b\u91cf:12",
    ])
    for i, a in enumerate(attrs):
        texts.append(RegionText(f"blessing_card_{i+1:02d}_attribute", a, 0.85))

    payload = parse_blessing_choice(texts, profile, None)
    assert payload and len(payload.options) == 20, f"FAIL: {len(payload.options) if payload else 0}"
    assert payload.selected_name and "35_01" in payload.selected_name, \
        f"FAIL: selected={payload.selected_name}"
    action = policy.decide_blessing_choice(payload, GameState(build_profile="power_focus"))
    assert "45" in action.reason, f"FAIL: {action.reason}"
    print("[OK] 20卡解析+选中匹配+策略=card_02(力量45)")

def test2():
    """并列值: card_01和card_06都是力量35, 详情面板匹配card_01"""
    texts = [
        RegionText("blessing_choice_anchor_archive", "\u661f\u8fb0\u6863\u6848", 0.95),
        RegionText("blessing_choice_detail_type", "\u529b\u91cf:35", 0.90),
        RegionText("blessing_card_01_attribute", "\u529b\u91cf:35", 0.85),
        RegionText("blessing_card_06_attribute", "\u529b\u91cf:35", 0.85),
        RegionText("blessing_card_02_attribute", "\u529b\u91cf:45", 0.85),
    ]
    payload = parse_blessing_choice(texts, profile, None)
    assert payload and payload.selected_name and "01" in payload.selected_name, \
        f"FAIL: {payload.selected_name}"
    print("[OK] 并列值: 详情面板匹配card_01非card_06")

def test3():
    """无详情面板OCR, 无图像, selected_name=None"""
    texts = [
        RegionText("blessing_choice_anchor_archive", "\u661f\u8fb0\u6863\u6848", 0.95),
        RegionText("blessing_card_01_attribute", "\u529b\u91cf:45", 0.85),
        RegionText("blessing_card_02_attribute", "\u529b\u91cf:35", 0.85),
    ]
    payload = parse_blessing_choice(texts, profile, None)
    assert payload and len(payload.options) == 2
    assert payload.selected_name is None, f"FAIL: {payload.selected_name}"
    print("[OK] 无详情面板+无图像: selected_name=None(等视觉fallback)")

test1()
test2()
test3()
print("done - 3/3")
