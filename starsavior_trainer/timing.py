# -*- coding: utf-8 -*-
"""环节计时器 — 量化 live loop 每帧各环节耗时(迁移计划 Phase 7 的 timing 部分)。

用法:
    timer = StageTimer(report_every=20)
    with timer.stage("classify"):
        ...
    timer.frame_done()   # 每帧末尾调用; 每 report_every 帧输出一次摘要 INFO 日志

摘要形如:
    timing #40: total avg=2.31s | classify avg=1.12s max=4.80s (48%) | ...
优化前先看数据, 不拍脑袋。
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator

from starsavior_trainer.logging_setup import get_logger

logger = get_logger("timing")


class StageTimer:
    def __init__(self, report_every: int = 20) -> None:
        self.report_every = max(1, report_every)
        self.frame_count = 0
        # 自上次汇报以来的各环节耗时样本(秒)。
        self._samples: dict[str, list[float]] = defaultdict(list)
        self._frame_started: float | None = None

    def frame_start(self) -> None:
        self._frame_started = time.perf_counter()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self._samples[name].append(time.perf_counter() - start)

    def record(self, name: str, seconds: float) -> None:
        """手动记一段耗时(主循环大段分支用 with 缩进不友好时)。"""
        self._samples[name].append(seconds)

    def frame_done(self) -> None:
        if self._frame_started is not None:
            self._samples["total"].append(time.perf_counter() - self._frame_started)
            self._frame_started = None
        self.frame_count += 1
        if self.frame_count % self.report_every == 0:
            self.report()

    def report(self) -> None:
        samples = self._samples
        if not samples:
            return
        total_sum = sum(samples.get("total", [])) or None
        parts: list[str] = []
        for name in sorted(samples, key=lambda n: -sum(samples[n])):
            values = samples[name]
            if not values:
                continue
            avg = sum(values) / len(values)
            piece = f"{name} avg={avg:.2f}s max={max(values):.2f}s"
            if total_sum and name != "total":
                piece += f" ({sum(values) / total_sum:.0%})"
            parts.append(piece)
        logger.info("timing #%d: %s", self.frame_count, " | ".join(parts))
        self._samples = defaultdict(list)
