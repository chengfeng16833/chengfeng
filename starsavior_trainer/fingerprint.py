# -*- coding: utf-8 -*-
"""像素指纹分类(取色宏思路) — 零 OCR 的毫秒级画面判定。

原理: 每个画面有一批"死忠像素"(按钮底色/面板边框/标题栏色块), 动效再闪它们也不动。
指纹 = 离线从带标签截图库自动挖出的 K 个取色点(画面内稳定 + 跨画面有区分度)。
运行时只做几百次 getpixel(亚毫秒), 全点命中且唯一 → 直接判定画面, 跳过整套 OCR 金字塔;
拿不准(0 或 ≥2 个候选) → 返回 None, 由原 OCR 路径兜底, 准确率不降。

指纹库: config/fingerprints/2560x1440.json, 由 tools/_mine_fingerprints.py 生成。
铁律: 指纹要么答对, 要么闭嘴 — 挖掘工具全库自检误判必须为 0 才落盘。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from starsavior_trainer.logging_setup import get_logger
from starsavior_trainer.models import Screen

logger = get_logger("fingerprint")

# 挖掘与运行时共用的基准分辨率(游戏实跑客户区, 见协作守则)。
BASE_SIZE: tuple[int, int] = (2560, 1440)


@dataclass(frozen=True)
class FingerprintPoint:
    x: int
    y: int
    rgb: tuple[int, int, int]
    tol: int

    def matches(self, pixel: tuple[int, int, int]) -> bool:
        return (
            abs(pixel[0] - self.rgb[0]) <= self.tol
            and abs(pixel[1] - self.rgb[1]) <= self.tol
            and abs(pixel[2] - self.rgb[2]) <= self.tol
        )


@dataclass(frozen=True)
class ScreenFingerprint:
    screen: Screen
    points: tuple[FingerprintPoint, ...]


def default_fingerprints_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "config"
        / "fingerprints"
        / f"{BASE_SIZE[0]}x{BASE_SIZE[1]}.json"
    )


def load_fingerprints(path: str | Path) -> dict[Screen, ScreenFingerprint]:
    """读指纹库 JSON → {Screen: ScreenFingerprint}。未知画面名跳过(向后兼容)。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    result: dict[Screen, ScreenFingerprint] = {}
    for screen_name, entry in data.get("screens", {}).items():
        try:
            screen = Screen(screen_name)
        except ValueError:
            logger.warning("指纹库包含未知画面 %s, 跳过", screen_name)
            continue
        points = tuple(
            FingerprintPoint(
                x=int(p["x"]),
                y=int(p["y"]),
                rgb=(int(p["rgb"][0]), int(p["rgb"][1]), int(p["rgb"][2])),
                tol=int(p["tol"]),
            )
            for p in entry.get("points", [])
        )
        if points:
            result[screen] = ScreenFingerprint(screen=screen, points=points)
    return result


def match_fingerprint(
    image: Image.Image,
    fingerprints: dict[Screen, ScreenFingerprint],
) -> Screen | None:
    """全点命中且全场唯一 → 该画面; 否则 None(交还 OCR)。

    坐标按 16:9 等比缩放适配非 2560x1440 的帧; 宽高比不同直接弃权
    (UI 布局会变, 取色点不再可信)。
    """
    if not fingerprints:
        return None
    width, height = image.size
    if width <= 0 or height <= 0:
        return None
    base_w, base_h = BASE_SIZE
    # 宽高比偏差 >2% 视为布局不同, 弃权。
    if abs(width * base_h - height * base_w) > 0.02 * base_w * base_h:
        return None
    scale_x = width / base_w
    scale_y = height / base_h

    if image.mode != "RGB":
        image = image.convert("RGB")

    candidates: list[Screen] = []
    for fingerprint in fingerprints.values():
        hit = True
        for point in fingerprint.points:
            x = min(int(point.x * scale_x), width - 1)
            y = min(int(point.y * scale_y), height - 1)
            if not point.matches(image.getpixel((x, y))):
                hit = False
                break
        if hit:
            candidates.append(fingerprint.screen)
            if len(candidates) > 1:
                # ≥2 个画面同时全命中 — 指纹库区分度不足, 宁可弃权。
                logger.debug("指纹歧义: %s 同时命中, 弃权", [c.value for c in candidates])
                return None
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# classify_hybrid 用的模块级缓存(每帧调用, 不能每次读 JSON)
# ---------------------------------------------------------------------------

_cached: dict[Screen, ScreenFingerprint] | None = None
_cache_loaded = False


def get_default_fingerprints() -> dict[Screen, ScreenFingerprint]:
    """惰性加载默认指纹库; 文件不存在/损坏 → 空 dict(指纹路径整体停用, 行为同旧版)。"""
    global _cached, _cache_loaded
    if not _cache_loaded:
        _cache_loaded = True
        path = default_fingerprints_path()
        try:
            _cached = load_fingerprints(path)
            logger.info("指纹库已加载: %d 个画面 (%s)", len(_cached), path.name)
        except FileNotFoundError:
            logger.info("无指纹库(%s 不存在), 指纹快路径停用", path)
            _cached = {}
        except Exception:
            logger.exception("指纹库加载失败, 指纹快路径停用")
            _cached = {}
    return _cached or {}
