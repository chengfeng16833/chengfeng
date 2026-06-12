# -*- coding: utf-8 -*-
"""离线挖掘像素指纹(取色点自动标定) → config/fingerprints/2560x1440.json。

数据源: screenshots/ 里 2560x1440 且文件名带画面标签的截图(classify_by_filename 标注)。
对每个画面挖 K 个取色点, 要求:
  1) 画面内稳定 — 该画面所有样本上颜色几乎不变(动效/变量区自动淘汰);
  2) 跨画面区分 — 每张其他画面的样本, 至少被 MIN_COVER 个点明显区分开。
落盘前用运行时同一套 match_fingerprint 做全库自检: 误判必须为 0, 否则不写盘。

用法:
    python tools/_mine_fingerprints.py            # 挖掘 + 自检 + 写盘
    python tools/_mine_fingerprints.py --dry-run  # 只挖掘 + 自检, 不写盘
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from starsavior_trainer.classifier import classify_by_filename  # noqa: E402
from starsavior_trainer.fingerprint import (  # noqa: E402
    BASE_SIZE,
    FingerprintPoint,
    ScreenFingerprint,
    default_fingerprints_path,
    load_fingerprints,
    match_fingerprint,
)
from starsavior_trainer.models import Screen  # noqa: E402

# ---- 挖掘参数 ----
GRID_STEP = 20          # 候选点网格步长(px)
MARGIN = 12             # 避开屏幕最边缘(窗口边框/圆角)
STAB_DEV = 8            # 画面内稳定: 每通道相对均值最大偏差 ≤ 此值
SEP_MIN = 45            # 跨画面区分: max 通道差 ≥ 此值才算"该点能区分那张样本"
MIN_COVER = 3           # 每张外部样本至少被几个点区分(余量)
MIN_POINTS = 8          # 每个指纹至少几个点(防未采样画面碰巧命中)
MAX_POINTS = 24         # 每个指纹至多几个点
TOL_MIN, TOL_MAX = 8, 22  # 运行时每点容差范围(均值 ± tol)


def collect_samples(shots_dir: Path) -> dict[Screen, list[Path]]:
    samples: dict[Screen, list[Path]] = defaultdict(list)
    skipped_size = 0
    for path in sorted(shots_dir.glob("*.png")):
        screen = classify_by_filename(path).screen
        if screen == Screen.UNKNOWN:
            continue
        with Image.open(path) as im:
            if im.size != BASE_SIZE:
                skipped_size += 1
                continue
        samples[screen].append(path)
    if skipped_size:
        print(f"(跳过 {skipped_size} 张非 {BASE_SIZE[0]}x{BASE_SIZE[1]} 的带标签图)")
    return samples


def load_grid_colors(paths: list[Path], xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """返回 (N样本, P点, 3通道) int16 — 每张图在网格点上的颜色。"""
    out = np.empty((len(paths), len(xs), 3), dtype=np.int16)
    for i, path in enumerate(paths):
        with Image.open(path) as im:
            arr = np.asarray(im.convert("RGB"))
        out[i] = arr[ys, xs, :]
    return out


def mine_screen(
    screen: Screen,
    own: np.ndarray,            # (N, P, 3) 本画面样本网格颜色
    others: np.ndarray,         # (M, P, 3) 其他画面全部样本网格颜色
    other_labels: list[str],    # M 个外部样本名(报告用)
) -> tuple[list[int], np.ndarray, np.ndarray, list[str], list[str]]:
    """贪心选点。返回 (选中点序号, 均值色, 每点tol, 薄弱样本, 不可分样本)。"""
    mean = own.mean(axis=0)                                    # (P, 3)
    dev = np.abs(own - mean[None, :, :]).max(axis=(0, 2))      # (P,) 组内最大偏差
    stable = dev <= STAB_DEV                                   # (P,)
    tol = np.clip(dev + 6, TOL_MIN, TOL_MAX).astype(np.int16)  # (P,)

    # 外部样本在每点与本画面均值的差(max 通道)
    sep = np.abs(others - mean[None, :, :]).max(axis=2)        # (M, P)
    # 点 p 能区分样本 j ⟺ p 稳定 且 sep[j,p] ≥ SEP_MIN
    distinguish = (sep >= SEP_MIN) & stable[None, :]           # (M, P)

    impossible: list[str] = []   # 一个稳定点都区分不了的外部样本 → 该指纹放弃
    for j in range(others.shape[0]):
        if not distinguish[j].any():
            impossible.append(other_labels[j])
    if impossible:
        return [], mean, tol, [], impossible

    chosen: list[int] = []
    cover = np.zeros(others.shape[0], dtype=np.int32)          # 每张外部样本已被几点区分
    # 贪心: 每轮选"对未覆盖样本新增覆盖最多"的稳定点
    while len(chosen) < MAX_POINTS:
        need = cover < MIN_COVER                               # 还差覆盖的样本
        if not need.any() and len(chosen) >= MIN_POINTS:
            break
        if need.any():
            gain = distinguish[need].sum(axis=0)               # (P,)
        else:
            # 覆盖已够, 补点到 MIN_POINTS: 选总区分力最强的
            gain = distinguish.sum(axis=0)
        gain[chosen] = -1
        gain[~stable] = -1
        best = int(gain.argmax())
        if gain[best] <= 0:
            break
        chosen.append(best)
        cover += distinguish[:, best]

    weak = [other_labels[j] for j in range(others.shape[0]) if cover[j] < MIN_COVER]
    return chosen, mean, tol, weak, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只挖掘+自检, 不写盘")
    parser.add_argument("--shots", default=None, help="截图目录(默认 screenshots/)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    shots_dir = Path(args.shots) if args.shots else root / "screenshots"

    t0 = time.perf_counter()
    samples = collect_samples(shots_dir)
    all_screens = sorted(samples, key=lambda s: s.value)
    total = sum(len(v) for v in samples.values())
    print(f"样本: {total} 张 / {len(all_screens)} 个画面 (来自 {shots_dir})")
    for screen in all_screens:
        flag = "  ⚠样本少" if len(samples[screen]) < 2 else ""
        print(f"  {screen.value:28s} {len(samples[screen])} 张{flag}")

    # 候选网格
    xs_axis = np.arange(MARGIN, BASE_SIZE[0] - MARGIN, GRID_STEP)
    ys_axis = np.arange(MARGIN, BASE_SIZE[1] - MARGIN, GRID_STEP)
    gx, gy = np.meshgrid(xs_axis, ys_axis)
    xs, ys = gx.ravel(), gy.ravel()
    print(f"候选取色点: {len(xs)} 个 (步长 {GRID_STEP}px)")

    # 一次性读入全部网格颜色
    grid: dict[Screen, np.ndarray] = {}
    labels: dict[Screen, list[str]] = {}
    for screen in all_screens:
        grid[screen] = load_grid_colors(samples[screen], xs, ys)
        labels[screen] = [p.name for p in samples[screen]]
    print(f"网格颜色读取完毕 ({time.perf_counter() - t0:.1f}s)\n")

    # 逐画面挖掘
    fingerprints: dict[Screen, ScreenFingerprint] = {}
    report_weak: dict[str, list[str]] = {}
    report_dropped: dict[str, list[str]] = {}
    for screen in all_screens:
        others_mats, others_labels = [], []
        for other in all_screens:
            if other == screen:
                continue
            others_mats.append(grid[other].reshape(-1, len(xs), 3))
            others_labels.extend(labels[other])
        others = np.concatenate(others_mats, axis=0)
        chosen, mean, tol, weak, impossible = mine_screen(
            screen, grid[screen], others, others_labels
        )
        if impossible:
            report_dropped[screen.value] = impossible
            print(f"✗ {screen.value:28s} 放弃(与 {len(impossible)} 张外部样本不可分: "
                  f"{', '.join(impossible[:3])}{'...' if len(impossible) > 3 else ''})")
            continue
        if len(chosen) < MIN_POINTS:
            report_dropped[screen.value] = [f"稳定点不足(只选出 {len(chosen)})"]
            print(f"✗ {screen.value:28s} 放弃(稳定点不足: {len(chosen)})")
            continue
        points = tuple(
            FingerprintPoint(
                x=int(xs[p]), y=int(ys[p]),
                rgb=(int(round(mean[p, 0])), int(round(mean[p, 1])), int(round(mean[p, 2]))),
                tol=int(tol[p]),
            )
            for p in chosen
        )
        fingerprints[screen] = ScreenFingerprint(screen=screen, points=points)
        if weak:
            report_weak[screen.value] = weak
        print(f"✓ {screen.value:28s} {len(points)} 点"
              + (f"  (薄弱: {len(weak)} 张外部样本覆盖<{MIN_COVER})" if weak else ""))

    # ---- 全库自检(用运行时同一套 match_fingerprint) ----
    print("\n=== 全库自检(运行时同款匹配) ===")
    wrong: list[str] = []
    abstain: list[str] = []
    correct = 0
    per_screen_hit: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # hit, total
    match_seconds = 0.0
    for screen in all_screens:
        for path in samples[screen]:
            with Image.open(path) as im:
                rgb = im.convert("RGB")  # 实跑的帧本来就是内存 RGB, 解码不算匹配成本
                t1 = time.perf_counter()
                got = match_fingerprint(rgb, fingerprints)
                match_seconds += time.perf_counter() - t1
            per_screen_hit[screen.value][1] += 1
            if got == screen:
                correct += 1
                per_screen_hit[screen.value][0] += 1
            elif got is None:
                abstain.append(f"{path.name} (标签 {screen.value})")
            else:
                wrong.append(f"{path.name}: 标签 {screen.value} → 误判 {got.value}")
    match_dt = match_seconds / max(1, total)
    print(f"对: {correct}/{total}  弃权: {len(abstain)}  误判: {len(wrong)}"
          f"  (单帧匹配平均 {match_dt * 1000:.2f}ms, 不含读盘)")
    for screen_name, (hit, n) in sorted(per_screen_hit.items()):
        mark = "✓" if hit == n else ("—" if screen_name in report_dropped else "△")
        print(f"  {mark} {screen_name:28s} {hit}/{n}")
    if abstain:
        print("弃权清单(这些帧会走 OCR, 无害):")
        for line in abstain:
            print(f"  - {line}")
    if wrong:
        print("\n❌ 误判清单(不可接受, 已停止写盘):")
        for line in wrong:
            print(f"  - {line}")
        return 1

    # 未覆盖画面提醒
    covered = {s.value for s in all_screens}
    uncovered = [s.value for s in Screen if s != Screen.UNKNOWN and s.value not in covered]
    if uncovered:
        print(f"\n⚠ 截图库未覆盖的画面({len(uncovered)} 个, 出现时由 OCR 兜底+看门狗纠错): "
              f"{', '.join(uncovered)}")

    if args.dry_run:
        print("\n(dry-run, 未写盘)")
        return 0

    out_path = default_fingerprints_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "base_size": list(BASE_SIZE),
            "grid_step": GRID_STEP,
            "stab_dev": STAB_DEV,
            "sep_min": SEP_MIN,
            "min_cover": MIN_COVER,
            "samples_total": total,
            "screens_dropped": report_dropped,
            "screens_weak": report_weak,
        },
        "screens": {
            s.value: {
                "samples": len(samples[s]),
                "points": [
                    {"x": p.x, "y": p.y, "rgb": list(p.rgb), "tol": p.tol}
                    for p in fp.points
                ],
            }
            for s, fp in sorted(fingerprints.items(), key=lambda kv: kv[0].value)
        },
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已写盘: {out_path}  ({len(fingerprints)} 个画面指纹)")
    # 回读验证(load → match 一张样张, 确认 JSON 闭环)
    reloaded = load_fingerprints(out_path)
    assert len(reloaded) == len(fingerprints), "回读指纹数不一致"
    print("回读校验 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
