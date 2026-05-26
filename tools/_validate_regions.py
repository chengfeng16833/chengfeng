# -*- coding: utf-8 -*-
"""验证 2560x1440.json 中所有区域坐标的合理性。"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\ChengFeng\Desktop\starsavior-trainer\config\regions\2560x1440.json"
data = json.loads(open(path, encoding='utf-8').read())

W, H = data["resolution"]
regions = data["regions"]
errors = []
warnings = []

for name, rect in regions.items():
    x, y, w, h = rect

    # 边界检查
    if x < 0 or y < 0:
        errors.append(f"[{name}] 坐标越界：x={x}, y={y}")
    if x + w > W:
        warnings.append(f"[{name}] 右边界越界：x+w={x+w} > {W}")
    if y + h > H:
        warnings.append(f"[{name}] 下边界越界：y+h={y+h} > {H}")
    if w <= 0 or h <= 0:
        errors.append(f"[{name}] 非法尺寸：{w}x{h}")
    if w > W or h > H:
        warnings.append(f"[{name}] 区域大于画面：{w}x{h} vs {W}x{H}")

# 检查是否有缺失的关键区域
required_prefixes = [
    "training_hub_", "training_select_", "post_training_", "rest_submenu_",
    "event_choice_", "commission_select_", "shop_item_", "region_move_",
    "battle_", "skill_select_",
]
missing = []
for prefix in required_prefixes:
    if not any(name.startswith(prefix) for name in regions):
        missing.append(prefix)

print(f"画面分辨率: {W}x{H}")
print(f"总区域数: {len(regions)}")
print()

if errors:
    print(f"错误 ({len(errors)}):")
    for e in errors:
        print(f"  ✗ {e}")
else:
    print("✓ 无错误")

if warnings:
    print(f"\n警告 ({len(warnings)}):")
    for w in warnings:
        print(f"  ⚠ {w}")
else:
    print("✓ 无警告")

if missing:
    print(f"\n缺失前缀 ({len(missing)}):")
    for m in missing:
        print(f"  ? {m}")

# 统计各前缀区域数
prefix_counts = {}
for name in regions:
    for sep in ('_card_', '_option_', '_item_', '_button', '_label', '_cost'):
        idx = name.rfind(sep)
        if idx > 0:
            base = name[:idx]
            if any(c.isdigit() for c in name[idx+len(sep):]):
                break
    else:
        base = name
    # 简化：按屏幕前缀分组
    for screen_prefix in required_prefixes:
        if name.startswith(screen_prefix.rstrip('_')):
            key = screen_prefix.rstrip('_')
            prefix_counts[key] = prefix_counts.get(key, 0) + 1
            break

print(f"\n屏幕前缀区域数:")
for key, count in sorted(prefix_counts.items()):
    print(f"  {key}: {count} 区域")
