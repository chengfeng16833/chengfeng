"""Live training loop: capture -> classify -> parse -> decide -> click.

Usage:
    python -m starsavior_trainer.cli.live_loop --dry-run
    python -m starsavior_trainer.cli.live_loop --profile config/regions/2560x1440.json --use-paddle --execute
    python -m starsavior_trainer.cli.live_loop --blue-mode --execute
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import time
from dataclasses import replace
from pathlib import Path

from PIL import Image

os.environ.setdefault("FLAGS_use_mkldnn", "0")
# Quiet noisy third-party loggers (PaddleOCR/paddle) WITHOUT muting our own
# starsavior.* logger. (Previously this was a blanket logging.disable(CRITICAL)
# that also silenced the trainer's logs.)
for _noisy in ("ppocr", "paddle", "paddlex", "PIL"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

from starsavior_trainer.capture import activate_window, capture_window, list_windows, save_image, WindowInfo
from starsavior_trainer.classifier import (
    classify_by_ocr,
    classify_by_blue_button,
    classify_hybrid,
    classify_journey_origin_by_visual,
    journey_origin_visual_scores,
)
from starsavior_trainer.training_inspector import TrainingInspector
from starsavior_trainer.shop_inspector import ShopInspector
from starsavior_trainer.commission_inspector import CommissionInspector
from starsavior_trainer.round_tracker import RoundTracker
from starsavior_trainer.timing import StageTimer
from starsavior_trainer.executor import (
    DryRunExecutor,
    PyAutoGuiExecutor,
    SendInputExecutor,
    map_action_to_rect,
)
from starsavior_trainer.image_regions import crop_region
from starsavior_trainer.logging_setup import get_logger
from starsavior_trainer.models import (
    Action,
    BattleScene,
    BlessingChoice,
    CommissionChoice,
    CommissionOption,
    GameState,
    Observation,
    Rect,
    RelicChoice,
    RelicOption,
    RestSubmenu,
    Screen,
    ShopScene,
    TrainingChoice,
    TrainingHubStatus,
)
from starsavior_trainer.ocr import NoopOcrEngine, PaddleOcrEngine, create_hybrid_ocr_engine
from starsavior_trainer.policy import TrainerPolicy, _is_iterable_of
from starsavior_trainer.regions import load_region_profile, scale_region_profile, RegionProfile
from starsavior_trainer.run_config import PreJourneyConfig
from starsavior_trainer.screen_reader import (
    PostTrainingResult,
    RegionOcrReader,
    parse_battle,
    parse_first_int,
    parse_blessing_choice,
    parse_blessing_setup,
    parse_character_select,
    parse_character_select_bbox,
    parse_commission_select,
    parse_confirm_dialog,
    parse_dialogue_scene,
    parse_event_choice,
    parse_event_fast_forward_setting,
    parse_journey_start,
    parse_post_training,
    parse_region_move,
    parse_rest_submenu,
    parse_shop,
    parse_skill_select,
    parse_training_direction,
    parse_training_hub,
    parse_training_select,
    parse_relic_choice,
)
from starsavior_trainer.vision import BlueButtonDetector, RingColorDetector
from starsavior_trainer.screens import HANDLERS

logger = get_logger("live_loop")


# "Tap to continue / skip" advance screens: after acting we re-capture almost
# immediately instead of waiting the full --interval, so the loop blows through
# reward popups / dialogue / post-training quickly (the user's "keep clicking to
# advance" request) — but still classifies before every click, so we never click
# blindly into the screen that comes next.
_ADVANCE_SCREENS = frozenset({Screen.DIALOGUE, Screen.POST_TRAINING, Screen.REWARD, Screen.GOAL_LIST})


# ---------------------------------------------------------------------------
# 帧哈希(提速3): 画面和上一帧几乎一样时跳过整屏 OCR 分类, 复用上帧结果。
# payload 每帧仍重读(检视器 +N 面板这类局部变化不能拿旧数据); UNKNOWN 不复用
# (静止的新画面必须反复重识别, 否则加了新锚也认不出来 → 卡死)。
# ---------------------------------------------------------------------------


def _append_training_log(round_no: int | None, reason: str, choices) -> None:
    """训练决策明细落盘(logs/training_log.csv, utf-8-sig 方便 Excel 直接开)。"""
    try:
        path = Path("logs/training_log.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()
        with path.open("a", encoding="utf-8-sig", newline="") as f:
            if is_new:
                f.write("时间,回合,决策,卡片明细(名称:加成:失败率:彩环)\n")
            detail = " | ".join(
                f"{c.name}:+{c.stat_gain}:fail={c.fail_rate if c.fail_rate is not None else '?'}:{c.ring}"
                for c in choices
            )
            stamp = time.strftime("%H:%M:%S")
            f.write(f'{stamp},{round_no if round_no is not None else "?"},"{reason}","{detail}"\n')
    except Exception:
        logger.debug("training_log.csv 写入失败", exc_info=True)


def _frame_signature(image: Image.Image) -> bytes:
    return image.convert("L").resize((32, 18)).tobytes()


def _frames_similar(a: bytes | None, b: bytes | None) -> bool:
    if not a or not b or len(a) != len(b):
        return False
    diff = sum(1 for x, y in zip(a, b) if abs(x - y) > 10)
    return diff <= len(a) * 0.01  # ≤1% 缩略像素变化视为同帧(动效画面自然超限)
_ADVANCE_SLEEP = 0.35
# TRAINING_SELECT: the inspector clicks 力量/体力/韧性 in quick succession on the
# SAME screen (no transition) — it only needs the preview gain to render, not the
# full --interval. Use a short re-capture sleep so picking a training is snappy.
_TRAINING_SELECT_SLEEP = 0.5


# ---------------------------------------------------------------------------
# F12 pause hotkey — lets the operator reclaim mouse/keyboard control mid-run
# ---------------------------------------------------------------------------


def _is_corner_point(x: int, y: int, width: int, height: int, margin: int = 120) -> bool:
    """True if (x, y) lies within ``margin`` px of ANY of the four screen corners.

    Robust emergency-stop predicate: a corner is "near a horizontal edge AND near
    a vertical edge" — so edge midpoints (near only one axis) don't count, but all
    four corner regions do. Unlike pyautogui's exact-pixel FAILSAFE this triggers
    on a whole region, so a quick mouse-slam reliably stops the bot.
    """
    near_left = x <= margin
    near_right = x >= width - margin
    near_top = y <= margin
    near_bottom = y >= height - margin
    return (near_left or near_right) and (near_top or near_bottom)


def _mouse_at_screen_corner(margin: int = 120) -> bool:
    """Read the OS cursor position and report whether it's in a screen corner.

    Used at the top of every loop iteration as a reliable manual stop that does
    NOT depend on pyautogui's call timing or exact-pixel FAILSAFE points. Never
    raises — any failure (non-Windows, ctypes issue) reports "not in corner" so
    the loop keeps running.
    """
    try:
        import ctypes
        from ctypes import wintypes

        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        width = ctypes.windll.user32.GetSystemMetrics(0)
        height = ctypes.windll.user32.GetSystemMetrics(1)
        return _is_corner_point(pt.x, pt.y, width, height, margin)
    except Exception:
        return False


class PauseController:
    """Toggle-able pause flag for the live loop, flipped by a global F12 hotkey.

    The main loop reads :pyattr:`paused` once per iteration; the hotkey
    callback runs on the ``keyboard`` library's listener thread and flips the
    flag.  A plain bool read/write is atomic in CPython, so no lock is needed.
    """

    def __init__(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def toggle(self) -> bool:
        """Flip the pause state and return the new value (bound to the hotkey)."""
        self._paused = not self._paused
        return self._paused

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False


def install_pause_hotkey(controller: PauseController, key: str = "f9") -> bool:
    """Register a global hotkey that toggles ``controller``'s pause state.

    Defaults to **F9**, not F12: F12 is Steam's default screenshot key and gets
    swallowed by Steam before our global hook ever sees it, so a F12 pause "did
    nothing". F9 is normally free.

    Binds with ``trigger_on_release=True`` so a slightly-held press can't fire
    the OS key-repeat several times and toggle the flag back to where it started
    (another "no effect" failure mode).

    Uses the ``keyboard`` library.  IMPORTANT: ``keyboard`` installs a
    low-level, system-wide keyboard hook.  Listening for a *global* hotkey can
    therefore require **running this console as Administrator** on Windows
    (and requires root on Linux); without sufficient privileges the hook may
    fail to register.

    This function never raises: if the library isn't installed, or the hook
    can't be registered (e.g. insufficient privileges), it logs/prints a
    warning and returns ``False`` so the caller keeps running normally — just
    without the hotkey.
    """
    try:
        import keyboard  # type: ignore  # lazy: only needed for the live hotkey
    except Exception as exc:  # ImportError or any other import-time failure
        msg = f"暂停热键不可用（keyboard 库导入失败: {exc}）。脚本将正常运行。"
        logger.warning(msg)
        print(f"[warn] {msg}")
        return False

    try:
        keyboard.add_hotkey(key, controller.toggle, trigger_on_release=True)
    except Exception as exc:  # registration failed — often needs admin rights
        msg = f"暂停热键注册失败（监听全局热键可能需要管理员权限运行: {exc}）。脚本将正常运行。"
        logger.warning(msg)
        print(f"[warn] {msg}")
        return False

    logger.info(f"{key.upper()} 暂停热键已启用。")
    print(f"{key.upper()} 暂停热键已启用：实跑中按 {key.upper()} 可暂停/恢复（夺回控制权）。")
    return True


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Starsavior live training loop.")
    parser.add_argument("--profile", default="config/regions/2560x1440.json", help="Region profile path.")
    parser.add_argument("--window-title", default="StarSavior", help="Game window title substring.")
    parser.add_argument("--execute", action="store_true", help="Execute clicks (default: dry-run).")
    parser.add_argument("--interval", type=float, default=3.0, help="Seconds between loop iterations.")
    parser.add_argument("--max-iterations", type=int, default=0, help="Max iterations (0 = unlimited).")
    parser.add_argument("--use-paddle", action="store_true", help="Use PaddleOCR (default: noop).")
    parser.add_argument("--blue-mode", action="store_true", help="Blue-button detection only (no OCR at all).")
    parser.add_argument("--hybrid-mode", action="store_true", help="Blue-button classification + OCR payload reading.")
    parser.add_argument("--list-windows", action="store_true", help="List windows and exit.")
    parser.add_argument("--verbose", action="store_true", help="Print OCR/color results for each region.")
    parser.add_argument("--character", default=None, help="Desired character name (Chinese), e.g. 克莱儿.")
    parser.add_argument(
        "--variant",
        default="",
        help="角色形态(同名多形态时区分): 留空=普通, ANOTHER=第二形态, COSMIC=系列。例: --variant COSMIC (罗莎莉亚).",
    )
    parser.add_argument(
        "--build-profile",
        default="balanced",
        help="Build profile: balanced, power_focus, focus_focus, durability_focus, stamina_tank, protection_focus.",
    )
    parser.add_argument("--difficulty", default="default", help="Journey difficulty selection for pre-journey setup.")
    parser.add_argument("--profession", default="", help="Character profession filter for pre-journey setup.")
    parser.add_argument(
        "--imprint-slot-1-index",
        type=int,
        default=1,
        help="1-based imprint index for setup slot 1.",
    )
    parser.add_argument(
        "--imprint-slot-2-index",
        type=int,
        default=1,
        help="1-based imprint index for setup slot 2.",
    )
    parser.add_argument("--support-deck", type=int, default=1, help="1-based support deck number for setup.")
    parser.add_argument("--friend-support-name", default="", help="Friend support card name to search/select.")
    parser.add_argument(
        "--prejourney",
        action="store_true",
        help="启用赛前全流程自动化(主界面→难度→职业筛选→刻印→卡组/好友卡→进旅途)。"
        "不开此开关时上述配置只记录不生效, 行为与旧版完全一致。",
    )
    parser.add_argument(
        "--executor",
        choices=("pyautogui", "sendinput"),
        default="pyautogui",
        help="真实点击的执行器: pyautogui(默认, 移动系统鼠标) / sendinput(Win32 SendInput, 点完还原光标)。",
    )
    parser.add_argument(
        "--ocr-engine",
        choices=("paddle", "hybrid", "noop"),
        default="paddle",
        help="OCR 引擎: paddle(默认) / hybrid(WinRT快路径+Paddle精读回退, 提速) / noop。",
    )
    return parser


def prejourney_config_from_args(args: argparse.Namespace) -> PreJourneyConfig:
    return PreJourneyConfig(
        difficulty=args.difficulty,
        character_name=args.character or "",
        profession=args.profession,
        imprint_slot_1_index=args.imprint_slot_1_index,
        imprint_slot_2_index=args.imprint_slot_2_index,
        support_deck=args.support_deck,
        friend_support_name=args.friend_support_name,
    )


def state_for_skill_learning(state: GameState, observation: Observation, policy: TrainerPolicy) -> GameState:
    """Enable final skill learning only after the D-DAY trading step is finished."""
    if observation.screen == Screen.SKILL_SELECT and getattr(policy, "_dday_trading_done", False):
        return replace(state, allow_skill_learning=True)
    if observation.screen in (Screen.INITIAL, Screen.CHARACTER_SELECT, Screen.TRAINING_HUB):
        return replace(state, allow_skill_learning=False)
    return state


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    prejourney_config = prejourney_config_from_args(args)

    if args.list_windows:
        _print_windows()
        return

    # Find window first
    window = _find_or_exit(args.window_title)
    base_profile = load_region_profile(args.profile)
    profile = base_profile
    policy = TrainerPolicy()
    training_inspector = TrainingInspector(max_fail_rate=policy.config.max_training_fail_rate)
    shop_inspector = ShopInspector()
    commission_inspector = CommissionInspector()
    state = GameState(
        desired_character=args.character,
        desired_variant=args.variant,
        build_profile=args.build_profile,
        # 只有显式 --prejourney 才把赛前配置塞进 state(钩子才会触发);
        # 不开开关 = 旧行为, 赛前参数仅记录在日志里。
        prejourney=prejourney_config if args.prejourney else None,
    )
    round_tracker = RoundTracker()
    if not args.execute:
        executor = DryRunExecutor()
    elif args.executor == "sendinput":
        executor = SendInputExecutor()
    else:
        executor = PyAutoGuiExecutor()
    ocr = _create_ocr(args.use_paddle, args.ocr_engine)
    # 分类专用引擎: hybrid 时复用同一对底层引擎但「信空」(空锚不回退 Paddle)。
    # timing 实测分类占帧 68% 的元凶就是空锚逐个回退; payload 精读仍用标准 ocr。
    classify_ocr = ocr
    if isinstance(ocr, HybridOcrEngine):
        classify_ocr = HybridOcrEngine(
            ocr.fast_engine, ocr.detailed_engine,
            fast_min_confidence=ocr.fast_min_confidence,
            fast_max_area=ocr.fast_max_area,
            fallback_on_empty=False,
        )
    blue_detector = BlueButtonDetector() if (args.blue_mode or args.hybrid_mode) else None

    if args.hybrid_mode:
        mode_label = "hybrid"
        args.use_paddle = True  # Hybrid mode needs real OCR
        if not isinstance(ocr, HybridOcrEngine):
            ocr = _create_ocr(True, args.ocr_engine)
            classify_ocr = ocr
            if isinstance(ocr, HybridOcrEngine):
                classify_ocr = HybridOcrEngine(
                    ocr.fast_engine, ocr.detailed_engine,
                    fast_min_confidence=ocr.fast_min_confidence,
                    fast_max_area=ocr.fast_max_area,
                    fallback_on_empty=False,
                )
    elif args.blue_mode:
        mode_label = "blue-button"
    elif args.use_paddle:
        mode_label = "paddle"
    else:
        mode_label = "noop"
    print(f"profile={base_profile.name} resolution={base_profile.resolution[0]}x{base_profile.resolution[1]} regions={len(base_profile.regions)}")
    print(f"mode={mode_label} execute={'yes' if args.execute else 'dry-run'}")
    print(f"character={args.character or '(auto)'} build_profile={args.build_profile}")
    print(
        "prejourney="
        f"difficulty={prejourney_config.difficulty} "
        f"profession={prejourney_config.profession or '(auto)'} "
        f"imprints={prejourney_config.imprint_slot_1_index},{prejourney_config.imprint_slot_2_index} "
        f"support_deck={prejourney_config.support_deck} "
        f"friend={prejourney_config.friend_support_name or '(none)'}"
    )
    print("build=journey-visual-guard-20260520a")
    print(f"game window: {window.title} ({window.rect.width}x{window.rect.height})")

    # F9 pause hotkey: lets the operator stop the bot's actions mid-run and
    # reclaim control without killing the process. Falls back gracefully (warns
    # and runs unpaused) if the hotkey can't be registered. (F12 is avoided — it's
    # Steam's screenshot key and gets swallowed before our hook sees it.)
    pause = PauseController()
    install_pause_hotkey(pause, key="f9")

    iteration = 0
    consecutive_character_confirms = 0
    last_character_click_target = None
    consecutive_unknown = 0
    was_paused = False
    # 提速1/3: 环节计时器(每20帧输出耗时摘要) + 帧哈希复用分类。
    timer = StageTimer(report_every=20)
    last_frame_sig: bytes | None = None
    last_screen: Screen | None = None
    last_screen_confidence: float = 0.0
    try:
        while args.max_iterations == 0 or iteration < args.max_iterations:
            # Mouse-corner emergency stop, checked FIRST every iteration. The most
            # reliable "reclaim control" path: move the mouse into any screen
            # corner and the bot exits cleanly. Beats both the keyboard hotkey
            # (swallowed by a focused admin/Steam window) and pyautogui's
            # exact-pixel FAILSAFE (needs a precise landing pixel at the exact
            # moment pyautogui is called) — this polls a whole corner region at
            # the top of the loop, independent of focus/privilege/timing.
            if args.execute and _mouse_at_screen_corner():
                print("\n[急停] 鼠标移到屏幕角落，已停止 bot，控制权交还。")
                return
            # While paused, do nothing but idle: no capture, no decision, no
            # click. Print once per second so it's clear the bot is waiting.
            if pause.paused:
                was_paused = True
                print("已暂停，按F9继续")
                time.sleep(1.0)
                continue
            if was_paused:
                print("已恢复")
                was_paused = False

            iteration += 1
            timer.frame_start()

            # Capture via PrintWindow (inside capture_window): works even when the
            # game is covered/unfocused, so we no longer hide the console or steal
            # focus just to grab a frame (dry-run is fully non-invasive now).
            _t0 = time.perf_counter()
            screenshot, client_window = capture_window(args.window_title)
            profile = scale_region_profile(base_profile, screenshot.size)
            reader = RegionOcrReader(profile, ocr)
            timer.record("capture", time.perf_counter() - _t0)

            print(f"\n--- iteration {iteration} ---")

            # Classify screen — 帧没变(哈希同)且上帧非 UNKNOWN 时直接复用,
            # 省掉整屏 OCR(提速3); 否则照常分类。
            _t0 = time.perf_counter()
            frame_sig = _frame_signature(screenshot)
            if (
                _frames_similar(frame_sig, last_frame_sig)
                and last_screen is not None
                and last_screen != Screen.UNKNOWN
            ):
                observation = Observation(screen=last_screen, confidence=last_screen_confidence)
                print("  (frame unchanged, classification reused)")
            elif args.hybrid_mode:
                observation = classify_hybrid(screenshot, profile, ocr)
            elif args.blue_mode:
                observation = classify_by_blue_button(screenshot, profile)
            elif args.use_paddle:
                # Default with real OCR: use hybrid (OCR + visual). Pure
                # classify_by_ocr CANNOT tell apart the journey-origin screens that
                # share the "旅程起点" title — character_select / blessing_setup /
                # journey_start — and always resolves to character_select. That made
                # the bot treat the blessing-setup screen as character select and
                # scroll forever looking for the runner (the "stuck on blessing"
                # freeze). Hybrid disambiguates them by visual content.
                observation = classify_hybrid(screenshot, profile, ocr)
            else:
                observation = classify_by_ocr(screenshot, profile, ocr)
            timer.record("classify", time.perf_counter() - _t0)
            last_frame_sig = frame_sig
            last_screen = observation.screen
            last_screen_confidence = observation.confidence

            logger.info(f"classified screen={observation.screen.value} confidence={observation.confidence:.2f}")
            if observation.screen in (Screen.CHARACTER_SELECT, Screen.BLESSING_SETUP):
                character_score, blessing_score = journey_origin_visual_scores(screenshot, profile)
                visual_screen = classify_journey_origin_by_visual(screenshot, profile)
                print(
                    "  journey_visual="
                    f"{visual_screen.value if visual_screen else 'unknown'} "
                    f"character_score={character_score:.2f} blessing_score={blessing_score:.2f}"
                )

            if observation.screen == Screen.UNKNOWN:
                unknown_path = Path("screenshots/live_unknown_latest.png")
                save_image(screenshot, unknown_path)
                consecutive_unknown += 1
                # 2026-06-12 提速(用户反馈: 剧情/展示页 bot 干等游戏自动跳过):
                # unknown 大多是转场/CG/展示页, 推进点几乎都在「底部中央」
                # (点击以继续 祖传位置: 获得奖励/目标列表/评鉴战结果同位),
                # 屏幕正中常是无效文字区 —— 底部为主, 每 3 次插一次中心兜底。
                # 上限 40(原 4 次太怂, 目标列表那类页面 4 次点不中就干等);
                # 真新画面卡死由监控的连续 unknown 告警兜底, 不靠这里放弃。
                if args.execute and consecutive_unknown <= 40:
                    activate_window(client_window.hwnd)
                    if consecutive_unknown % 3 == 0:
                        cx = client_window.rect.x + client_window.rect.width // 2
                        cy = client_window.rect.y + client_window.rect.height // 2
                        spot = "centre"
                    else:
                        cx = client_window.rect.x + client_window.rect.width // 2
                        cy = client_window.rect.y + int(client_window.rect.height * 0.88)
                        spot = "bottom"
                    executor.execute(
                        Action("click", Rect(cx, cy, 1, 1), f"unknown: click {spot} to advance", repeat=2)
                    )
                    print(f"  unknown screen, click {spot} to advance ({consecutive_unknown})")
                    timer.frame_done()
                    # 转场/展示页用快节奏重试, 不睡满 --interval(提速主力)。
                    time.sleep(_ADVANCE_SLEEP)
                else:
                    print(f"  unknown screen, pausing (consecutive={consecutive_unknown})")
                    timer.frame_done()
                    time.sleep(args.interval)
                continue
            consecutive_unknown = 0

            # Parse payload
            _t0 = time.perf_counter()
            if args.blue_mode:
                payload = _read_screen_payload_blue(observation.screen, screenshot, profile, blue_detector, args.verbose)
            elif args.hybrid_mode:
                payload = _read_screen_payload_ocr(observation.screen, screenshot, profile, reader, args.verbose)
            else:
                payload = _read_screen_payload_ocr(observation.screen, screenshot, profile, reader, args.verbose)

            timer.record("parse", time.perf_counter() - _t0)

            if payload is not None:
                observation = Observation(screen=observation.screen, confidence=observation.confidence, payload=payload)
                if isinstance(payload, BlessingChoice):
                    print(
                        "  blessing_options="
                        + ", ".join(
                            f"{option.name}:value={option.value}:sub={option.sub_blessing_count}"
                            for option in payload.options
                        )
                        + f" detail_sub={payload.detail_sub_blessing_count}"
                    )
            elif args.verbose:
                print("  (no payload parsed)")

            # Diagnostic: the intro_story skip target (top-right) can collide with a
            # HUD screen's menu button — save the frame whenever we classify
            # intro_story so a mis-classified HUD-dialogue can be inspected offline.
            if observation.screen == Screen.DIALOGUE and getattr(observation.payload, "variant", "") == "intro_story":
                save_image(screenshot, Path("screenshots/live_intro_story_latest.png"))

            # Round tracking: the hub shows no turn counter, only a date — count
            # date changes as rounds (drives the early-game training bias). Reset
            # when a new journey is being set up (initial / character select).
            if observation.screen in (Screen.INITIAL, Screen.CHARACTER_SELECT):
                round_tracker.reset()
            if observation.screen == Screen.TRAINING_HUB and isinstance(observation.payload, TrainingHubStatus):
                round_tracker.observe_date(observation.payload.turn_label)
                # 从大厅 "RANK 21" 读角色综合等级 → 委托选阶用(选建议等级≤它的最高阶)。
                rank_num = parse_first_int(observation.payload.rank_label or "")
                if rank_num is not None:
                    state = replace(state, character_rank=rank_num)
            state = replace(state, current_round=round_tracker.current_round)
            state = state_for_skill_learning(state, observation, policy)
            print(f"  current_round={round_tracker.current_round}")

            # Decide
            _t0 = time.perf_counter()
            action = None
            # BLESSING_CHOICE goes through the policy (decide_blessing_choice): pick the
            # highest-value blessing, same-value → topmost, two-step confirm. The old
            # click-to-read-sub inspector looped in-game (sub count flickers, candidate
            # list OCR jitters), so it's retired — see 协作守则 / commit.
            # Training: heads are random each turn, so inspect 力量/体力/韧性 (click
            # each to reveal its +N gain) and pick whichever gives the most — a
            # fixed bias can't know this turn's best. Mirrors the blessing inspector.
            if observation.screen == Screen.TRAINING_SELECT and _is_iterable_of(observation.payload, TrainingChoice):
                # 校准素材: 最近一帧训练选择画面(人头列几何标定用)。
                save_image(screenshot, Path("screenshots/live_training_select_latest.png"))
                # 前期(≤12回合)人头优先(2026-06-12 用户策略): 力量/韧性里跟着
                # 支援卡人头练刷好感, 不逐卡检视。不可用(返回None)回退检视器。
                if round_tracker.current_round is not None and round_tracker.current_round <= 12:
                    action = policy.decide_training_early_icons(observation.payload, state)
                    if action is not None:
                        icons = {c.attr: c.icon_count for c in observation.payload}
                        print(f"  early_icons={icons} round={round_tracker.current_round}")
                if action is None:
                    action = training_inspector.decide(observation.payload, state)
                    if action is not None:
                        print(f"  training_inspector_records={training_inspector.records} pending={training_inspector.pending}")
            elif observation.screen != Screen.TRAINING_SELECT:
                training_inspector.reset()
                policy._early_icon_rejected.clear()
            # Journey Trading: item effects only show when an item is selected, so
            # the inspector clicks each row to read its effect, then buys by effect
            # (回体力/潜质点退还) — mirrors the training inspector.
            if observation.screen == Screen.SHOP and isinstance(observation.payload, ShopScene):
                action = shop_inspector.decide(observation.payload, policy)
                if action is not None:
                    print(
                        f"  shop_inspector effects={shop_inspector.effects} "
                        f"pending={shop_inspector.pending_index} bought={shop_inspector.bought_effects} "
                        f"selected_effect={observation.payload.selected_effect!r}"
                    )
            elif observation.screen != Screen.SHOP:
                shop_inspector.reset()
            # Commission: the list shows only tier names; the suggested rank shows
            # only in the detail once a commission is selected, so inspect each by
            # clicking it, read its 建议综合等级, then accept the highest tier whose
            # suggested rank ≤ character rank. Mirrors the training inspector. Falls
            # back to the policy (returns None) when the character rank is unknown.
            if observation.screen == Screen.COMMISSION_SELECT and isinstance(observation.payload, CommissionChoice):
                action = commission_inspector.decide(observation.payload, state)
                if action is not None:
                    print(
                        f"  commission_inspector_records={commission_inspector.records} "
                        f"pending={commission_inspector.pending} "
                        f"char_rank={observation.payload.character_rank} "
                        f"suggested={observation.payload.selected_suggested_rank}"
                    )
            elif observation.screen != Screen.COMMISSION_SELECT:
                commission_inspector.reset()
            if action is None:
                action = policy.decide(state, observation)
            if observation.screen == Screen.CHARACTER_SELECT and action.kind == "click":
                character_path = Path("screenshots/live_character_select_latest.png")
                save_image(screenshot, character_path)
                # Only a *repeated identical* click means we're genuinely stuck.
                # The normal flow clicks two different targets — select the
                # character row, then the 选择 confirm button — which is progress,
                # not a loop, so it must not be blocked.
                if action.target == last_character_click_target:
                    consecutive_character_confirms += 1
                else:
                    consecutive_character_confirms = 1
                    last_character_click_target = action.target
                if consecutive_character_confirms >= 3:
                    action = Action("pause", None, f"repeated identical character click blocked, saved {character_path}")
            else:
                consecutive_character_confirms = 0
                last_character_click_target = None
            timer.record("decide", time.perf_counter() - _t0)
            # 决策日志带回合号: 复盘训练策略时能按回合对齐(用户 2026-06-12 需求)。
            logger.info(
                f"decision: {action.kind} round={round_tracker.current_round} "
                f"target={action.target} reason={action.reason}"
            )
            # 训练回合明细 CSV(logs/training_log.csv, Excel 可直接开): 每次最终
            # 确认训练时落一行 = 回合号 + 选择理由 + 五张卡的 加成/失败率/彩环。
            if (
                observation.screen == Screen.TRAINING_SELECT
                and action.kind == "click"
                and "confirm training" in (action.reason or "")
                and _is_iterable_of(observation.payload, TrainingChoice)
            ):
                _append_training_log(round_tracker.current_round, action.reason, observation.payload)
            screen_action = map_action_to_rect(action, screenshot.size, client_window.rect)
            if action.target is not None:
                print(f"  screen_target={screen_action.target}")

            # Execute. Activate the game first so the synthetic click/scroll lands
            # on it: Unity ignores input while inactive, and the mouse-wheel message
            # is routed to the focused window. Only when actually executing, so
            # dry-run / diagnosis stays non-invasive.
            if args.execute and action.kind in ("click", "move", "scroll"):
                # Emergency stop, checked AGAIN right before we move the mouse: the
                # top-of-loop check can be "beaten" because execute's moveTo yanks
                # the cursor back to a game target, so a corner-slam during the
                # (multi-second) OCR phase would be overwritten before the next
                # top check sees it. Checking here — the last moment before we grab
                # the mouse — catches a corner-slam from any point in the iteration.
                if _mouse_at_screen_corner():
                    print("\n[急停] 鼠标移到屏幕角落，已停止 bot，控制权交还。")
                    return
                activate_window(client_window.hwnd)
            _t0 = time.perf_counter()
            result = executor.execute(screen_action)
            timer.record("execute", time.perf_counter() - _t0)
            logger.info(f"executed: {result.kind} point={result.point} executed={result.executed}")
            timer.frame_done()

            # Advance screens (reward / dialogue / post-training) re-capture fast so
            # we don't crawl one click per --interval through them.
            if observation.screen in _ADVANCE_SCREENS:
                time.sleep(_ADVANCE_SLEEP)
            elif observation.screen == Screen.TRAINING_SELECT:
                time.sleep(min(_TRAINING_SELECT_SLEEP, args.interval))
            else:
                time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nstopped by user")
    except RuntimeError as exc:
        print(f"\nerror: {exc}")
    except Exception as exc:
        # pyautogui FAILSAFE: operator slammed the mouse into a screen corner to
        # abort. This is the reliable "reclaim control" path (the keyboard hotkey
        # can be swallowed by a focused admin/Steam window). Exit cleanly instead
        # of dumping a traceback.
        if type(exc).__name__ == "FailSafeException":
            print("\n[FAILSAFE] 鼠标移到屏幕角落，已紧急停止 bot。控制权交还。")
            return
        raise


# ---------------------------------------------------------------------------
# OCR-mode screen reading (existing logic)
# ---------------------------------------------------------------------------


def _read_screen_payload_ocr(
    screen: Screen,
    image,
    profile: RegionProfile,
    reader: RegionOcrReader,
    verbose: bool,
) -> object | None:
    # Dispatch through the screen registry: each handler declares which region
    # prefixes to OCR and how to parse them, replacing the old per-screen if/elif.
    # Character select scrolls by dragging to arbitrary (half-row) offsets, so
    # fixed-row OCR fails. Locate names by OCR bounding box instead.
    if screen == Screen.CHARACTER_SELECT:
        payload = parse_character_select_bbox(image, profile, reader.ocr)
        if verbose and payload is not None:
            print(f"  bbox names: {[o.name for o in payload.options if o.name != payload.selected_name]}")
        return payload

    handler = HANDLERS.get(screen)
    if handler is None or handler.ocr_prefixes is None:
        return None

    region_texts = reader.read_prefixes(image, handler.ocr_prefixes, max_area=160000)
    if verbose:
        for rt in region_texts:
            print(f"  ocr {rt.name}: '{rt.text}' ({rt.confidence:.2f})")

    return handler.parse(region_texts, profile, image, ocr=reader.ocr)


# ---------------------------------------------------------------------------
# Blue-mode screen reading (color-only, no OCR)
# ---------------------------------------------------------------------------


def _read_screen_payload_blue(
    screen: Screen,
    image,
    profile: RegionProfile,
    detector: BlueButtonDetector,
    verbose: bool,
) -> object | None:
    """Build screen payloads using only color detection — no OCR.

    For simple screens the policy just clicks a known button — no payload needed.
    For complex screens we use color-based heuristics (ring detection, red text, etc).
    """
    # Dispatch through a local builder table instead of a per-screen if/elif.
    # (Blue builders live in this module; they stay local for now and move into
    # the screen handlers during the deferred physical migration — see REFACTOR.md.)
    builder = _BLUE_PARSERS.get(screen)
    if builder is None:
        # Simple screens: INITIAL, CHARACTER_SELECT, BLESSING_SETUP, BLESSING_CHOICE,
        # JOURNEY_START, CONFIRM_DIALOG, EVENT_FAST_FORWARD_SETTING, REGION_MOVE —
        # policy clicks a hardcoded button; no payload needed.
        return None
    return builder(image, profile, detector, verbose)


def _shop_blue(image, profile, detector, verbose):
    # Shop needs item names/prices — skip without OCR.
    if verbose:
        print("  shop: skipping (no OCR, can't read items)")
    return None


def _training_hub_blue(image, profile: RegionProfile) -> TrainingHubStatus:
    """Minimal TrainingHubStatus — policy clicks the training button."""
    has_commission_alert = False
    has_shop_alert = False
    alert_rect = profile.regions.get("training_hub_commission_alert")
    if alert_rect is not None:
        try:
            from starsavior_trainer.screen_reader import _detect_red_text

            has_commission_alert = _detect_red_text(crop_region(image, alert_rect))
        except Exception as e:
            logger.debug(f"[_training_hub_blue] commission alert detect failed: {e}")
            pass

    shop_alert_rect = profile.regions.get("training_hub_shop_alert")
    if shop_alert_rect is not None:
        try:
            from starsavior_trainer.screen_reader import _detect_yellow_text

            has_shop_alert = _detect_yellow_text(crop_region(image, shop_alert_rect))
        except Exception as e:
            logger.debug(f"[_training_hub_blue] shop alert detect failed: {e}")
            pass

    return TrainingHubStatus(
        training_button=profile.regions.get("training_hub_action_training"),
        commission_button=profile.regions.get("training_hub_action_commission"),
        rest_button=profile.regions.get("training_hub_action_rest"),
        skill_button=profile.regions.get("training_hub_nav_potential"),
        shop_button=profile.regions.get("training_hub_action_shop"),
        has_commission_alert=has_commission_alert,
        has_shop_alert=has_shop_alert,
    )


def _training_select_blue(image, profile: RegionProfile, verbose: bool) -> list[TrainingChoice] | None:
    """Read training options using only ring color detection (no OCR for stat_gain/fail_rate).

    Without OCR we can't read stat_gain or fail_rate — set them to 0 (safe defaults).
    Ring color detection still works and influences scoring.
    """
    TRAINING_CARD_ATTRIBUTES = ("power", "stamina", "guts", "wisdom", "speed")
    choices: list[TrainingChoice] = []
    ring_detector = RingColorDetector()
    confirm_button = profile.regions.get("training_select_confirm_button")
    back_button = profile.regions.get("top_back_button")

    for attr in TRAINING_CARD_ATTRIBUTES:
        card_rect = profile.regions.get(f"training_select_card_{attr}")
        if card_rect is None:
            continue

        ring = "none"
        ring_rect = profile.regions.get("training_select_ring_detect")
        if ring_rect is not None:
            try:
                ring_signal = ring_detector.detect(crop_region(image, ring_rect))
                ring = ring_signal.name
            except Exception as e:
                logger.debug(f"[_training_select_blue] ring detect failed for {attr}: {e}")
                pass

        choices.append(
            TrainingChoice(
                name=attr,
                stat_gain=0,
                ring=ring,
                fail_rate=None,  # blue mode reads no 失败率 → unknown, not 0%
                target=card_rect,
                confirm_button=confirm_button,
                back_button=back_button,
            )
        )

    if verbose:
        for c in choices:
            print(f"  training {c.name}: ring={c.ring}")

    return choices if choices else None


def _rest_submenu_blue(
    image,
    profile: RegionProfile,
    detector: BlueButtonDetector,
    verbose: bool,
) -> RestSubmenu | None:
    """Build rest submenu payload using blue button detection for option selection.

    Without OCR for coin count, we check if the meditation option (option 3)
    has an active blue button. If yes → has_meditation_room=True and coins assumed high.
    Otherwise fall back to option 2.
    """
    meditation_rect = profile.regions.get("rest_submenu_option_3")
    rough_sleep_rect = profile.regions.get("rest_submenu_option_1")
    free_sleep_rect = profile.regions.get("rest_submenu_option_1")

    # Check if meditation room button is active (blue/enabled)
    has_meditation = False
    if meditation_rect is not None:
        try:
            signal = detector.detect(crop_region(image, meditation_rect))
            has_meditation = signal.name == "active_blue"
        except Exception as e:
            logger.debug(f"[_rest_submenu_blue] meditation detect failed: {e}")
            has_meditation = True  # Assume available if we can't detect

    # Without OCR, assume coins are sufficient for the best available option.
    coins = 100 if has_meditation else 40

    if verbose:
        print(f"  rest: meditation={'available' if has_meditation else 'unavailable'} coins={coins}")

    return RestSubmenu(
        coins=coins,
        has_meditation_room=has_meditation,
        meditation_room=meditation_rect or rough_sleep_rect or Rect(0, 0, 1, 1),
        rough_sleep=rough_sleep_rect or free_sleep_rect or Rect(0, 0, 1, 1),
        lodging=profile.regions.get("rest_submenu_option_2"),
        confirm_button=profile.regions.get("rest_submenu_confirm_button"),
    )


def _commission_select_blue(
    image,
    profile: RegionProfile,
    verbose: bool,
) -> CommissionChoice | None:
    """Read commission options using red-text color detection only."""
    from starsavior_trainer.screen_reader import _detect_red_text

    options: list[CommissionOption] = []
    for idx in range(1, 6):
        target = profile.regions.get(f"commission_select_option_{idx}")
        if target is None:
            continue

        has_red = False
        red_rect = profile.regions.get(f"commission_select_option_{idx}_red_text")
        if red_rect is not None:
            try:
                has_red = _detect_red_text(crop_region(image, red_rect))
            except Exception as e:
                logger.debug(f"[_commission_select_blue] red detect failed for option {idx}: {e}")
                pass

        options.append(
            CommissionOption(
                name=f"commission_{idx}",
                rank="?",
                has_red_text=has_red,
                target=target,
            )
        )

    if verbose:
        for o in options:
            print(f"  commission {o.name}: red_text={o.has_red_text}")

    if not options:
        return None
    accept_btn = profile.regions.get("commission_select_accept_button")
    return CommissionChoice(options=options, accept_button=accept_btn)


def _relic_choice_blue(
    profile: RegionProfile,
    detector: BlueButtonDetector,
    image,
) -> RelicChoice | None:
    """Build a minimal relic choice — without OCR, pick the middle card."""
    options: list[RelicOption] = []
    for idx in range(1, 4):
        target = profile.regions.get(f"relic_choice_card_{idx}")
        if target is None:
            continue
        options.append(RelicOption(name=f"relic_{idx}", score=idx, target=target))

    if not options:
        return None

    confirm_rect = profile.regions.get("relic_choice_confirm_button")
    confirm_active = False
    if confirm_rect is not None and image is not None:
        try:
            signal = detector.detect(crop_region(image, confirm_rect))
            confirm_active = signal.name == "active_blue"
        except Exception as e:
            logger.debug(f"[_relic_choice_blue] confirm detect failed: {e}")
            pass

    # If confirm is active, a relic was already selected.
    selected_name = "relic_2" if confirm_active else None

    return RelicChoice(
        options=options,
        confirm_button=confirm_rect,
        selected_name=selected_name,
    )


def _event_choice_blue(
    image,
    profile: RegionProfile,
    verbose: bool,
) -> list | None:
    """Build minimal event choice options — pick option 1 as default."""
    from starsavior_trainer.models import EventOption

    options: list[EventOption] = []
    for idx in range(1, 5):
        target = profile.regions.get(f"event_choice_option_{idx}")
        if target is None:
            continue
        options.append(EventOption(text=f"option_{idx}", target=target))

    if verbose:
        print(f"  event_choice: {len(options)} options available")

    return options if options else None


def _dialogue_blue(profile: RegionProfile):
    """Return a minimal dialogue scene using the journey skip button."""
    from starsavior_trainer.models import DialogueScene

    skip_rect = profile.regions.get("dialogue_journey_skip_button")
    if skip_rect is None:
        skip_rect = profile.regions.get("dialogue_intro_skip_button")
    if skip_rect is not None:
        return DialogueScene(skip_button=skip_rect, variant="journey_hud")
    return None


# Blue-mode payload builders by screen. Adapter lambdas give them a uniform
# (image, profile, detector, verbose) signature. Screens not listed need no
# payload in blue mode (policy clicks a fixed button).
_BLUE_PARSERS = {
    Screen.TRAINING_HUB: lambda image, profile, detector, verbose: _training_hub_blue(image, profile),
    Screen.TRAINING_SELECT: lambda image, profile, detector, verbose: _training_select_blue(image, profile, verbose),
    Screen.REST_SUBMENU: lambda image, profile, detector, verbose: _rest_submenu_blue(image, profile, detector, verbose),
    Screen.COMMISSION_SELECT: lambda image, profile, detector, verbose: _commission_select_blue(image, profile, verbose),
    Screen.RELIC_CHOICE: lambda image, profile, detector, verbose: _relic_choice_blue(profile, detector, image),
    Screen.SHOP: _shop_blue,
    Screen.EVENT_CHOICE: lambda image, profile, detector, verbose: _event_choice_blue(image, profile, verbose),
    Screen.DIALOGUE: lambda image, profile, detector, verbose: _dialogue_blue(profile),
    Screen.BATTLE: lambda image, profile, detector, verbose: parse_battle([], profile, image),
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _screen_to_prefix(screen: Screen) -> str | None:
    mapping = {
        Screen.DIALOGUE: "dialogue",
        Screen.CHARACTER_SELECT: "character",
        Screen.BLESSING_SETUP: "blessing",
        Screen.BLESSING_CHOICE: "blessing",
        Screen.JOURNEY_START: "journey_start",
        Screen.CONFIRM_DIALOG: "confirm_dialog",
        Screen.EVENT_FAST_FORWARD_SETTING: "event_fast_forward",
        Screen.TRAINING_HUB: "training_hub",
        Screen.TRAINING_SELECT: "training_select",
        Screen.REST_SUBMENU: "rest_submenu",
        Screen.EVENT_CHOICE: "event_choice",
        Screen.COMMISSION_SELECT: "commission_select",
        Screen.SHOP: "shop_item",
        Screen.BATTLE: "battle",
        Screen.SKILL_SELECT: "skill_select",
        Screen.POST_TRAINING: "post_training",
        Screen.REGION_MOVE: "region_move",
        Screen.RELIC_CHOICE: "relic_choice",
    }
    return mapping.get(screen)


def _create_ocr(use_paddle: bool, engine: str = "paddle"):
    if engine == "hybrid":
        # 提速2: WinRT 快路径(实测区域级 0.01-0.04s, Paddle 0.3-0.5s)+
        # Paddle 精读回退。winsdk 缺失/任一引擎不可用时自动降级, 永不崩。
        return create_hybrid_ocr_engine()
    if use_paddle:
        try:
            return PaddleOcrEngine()
        except RuntimeError as exc:
            print(f"warning: PaddleOCR not available ({exc}), falling back to noop")
    return NoopOcrEngine()


def _find_or_exit(title: str) -> WindowInfo:
    windows = list_windows()
    for win in windows:
        if title.casefold() in win.title.casefold():
            return win
    print(f"window '{title}' not found. Available windows:")
    _print_windows()
    raise SystemExit(1)


def _print_windows() -> None:
    for win in sorted(list_windows(), key=lambda w: w.title.casefold()):
        print(f"  {win.hwnd} {win.rect.width}x{win.rect.height} {win.title}")


if __name__ == "__main__":
    main()
