"""Global control panel for the Starsavior trainer.

A single Tkinter window (ttk.Notebook tabs) that wraps every CLI tool in the
project — live training loop, screenshot/window capture, region calibration,
OCR reading, offline harness, manifest replay, and the unit-test runner.

Each action builds a command and launches it as a subprocess; output is
streamed into one shared log.  Only one subprocess runs at a time.  No extra
dependencies beyond the Python standard library.

Run with:
    python -m starsavior_trainer.cli.gui
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Project root = two levels up from this file (…/starsavior_trainer/cli/gui.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGIONS_DIR = PROJECT_ROOT / "config" / "regions"
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
CHARACTERS_FILE = PROJECT_ROOT / "config" / "characters.json"

BUILD_PROFILES = (
    "balanced",
    "power_focus",
    "focus_focus",
    "durability_focus",
    "stamina_tank",
    "protection_focus",
)

# (label, cli flag) — flag is empty for the default OCR (paddle) mode.
CLASSIFY_MODES = (
    ("Hybrid (蓝键分类 + OCR)", "--hybrid-mode"),
    ("Blue button only (纯蓝键)", "--blue-mode"),
    ("Paddle OCR", "--use-paddle"),
    ("Noop (无 OCR)", ""),
)


def _list_region_profiles() -> list[str]:
    if not REGIONS_DIR.is_dir():
        return ["config/regions/2560x1440.json"]
    rels = [str(p.relative_to(PROJECT_ROOT)).replace("\\", "/") for p in sorted(REGIONS_DIR.glob("*.json"))]
    return rels or ["config/regions/2560x1440.json"]


def _default_profile(profiles: list[str]) -> str:
    for p in profiles:
        if "2560x1440" in p:
            return p
    return profiles[0]


def _load_characters() -> list[dict[str, str]]:
    """Load the character roster from config/characters.json.

    Returns a list of {"name", "profile", "note"} dicts.  Missing or malformed
    file yields an empty roster (UI still allows typing a name manually).
    """
    try:
        data = json.loads(CHARACTERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    roster: list[dict[str, str]] = []
    for entry in data.get("characters", []):
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        roster.append(
            {
                "name": name,
                "profile": str(entry.get("profile", "balanced")).strip() or "balanced",
                "note": str(entry.get("note", "")).strip(),
            }
        )
    return roster


class TrainerGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Starsavior Trainer 全局控制台")
        self.root.geometry("1000x760")
        self.root.minsize(840, 620)

        self.process: subprocess.Popen[str] | None = None
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self._action_buttons: list[ttk.Button] = []

        self.profiles = _list_region_profiles()
        self.char_roster = _load_characters()
        self.char_profile_map = {c["name"]: c["profile"] for c in self.char_roster}

        self._build_layout()
        self._poll_log_queue()

    # ----------------------------------------------------------- layout
    def _build_layout(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=False, padx=6, pady=(6, 0))

        self._build_tab_live(notebook)
        self._build_tab_capture(notebook)
        self._build_tab_calibrate(notebook)
        self._build_tab_offline(notebook)
        self._build_tab_tests(notebook)

        # --- bottom control bar (shared) ---
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=6, pady=4)
        self.stop_btn = ttk.Button(bar, text="■ 停止当前进程", command=self.stop_process, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(bar, text="清空日志", command=self.clear_log).pack(side="left", padx=4)
        self.status = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=self.status, anchor="w").pack(side="left", padx=12)

        # --- shared log ---
        log_frame = ttk.LabelFrame(self.root, text="日志")
        log_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.log = scrolledtext.ScrolledText(log_frame, wrap="word", height=16, font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.configure(state="disabled")

    def _register_action(self, btn: ttk.Button) -> ttk.Button:
        self._action_buttons.append(btn)
        return btn

    # ----------------------------------------------------- tab: live loop
    def _build_tab_live(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb)
        nb.add(tab, text="训练循环")
        pad = {"padx": 6, "pady": 4}

        ttk.Label(tab, text="窗口标题:").grid(row=0, column=0, sticky="e", **pad)
        self.window_title = tk.StringVar(value="StarSavior")
        ttk.Entry(tab, textvariable=self.window_title, width=22).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(tab, text="间隔(秒):").grid(row=0, column=2, sticky="e", **pad)
        self.interval = tk.StringVar(value="2.0")
        ttk.Spinbox(tab, from_=0.5, to=10.0, increment=0.5, textvariable=self.interval, width=6).grid(
            row=0, column=3, sticky="w", **pad
        )

        ttk.Label(tab, text="最大轮次(0=无限):").grid(row=0, column=4, sticky="e", **pad)
        self.max_iter = tk.StringVar(value="0")
        ttk.Spinbox(tab, from_=0, to=9999, increment=1, textvariable=self.max_iter, width=6).grid(
            row=0, column=5, sticky="w", **pad
        )

        ttk.Label(tab, text="区域配置:").grid(row=1, column=0, sticky="e", **pad)
        self.live_profile = tk.StringVar(value=_default_profile(self.profiles))
        ttk.Combobox(tab, textvariable=self.live_profile, values=self.profiles, width=42, state="readonly").grid(
            row=1, column=1, columnspan=5, sticky="we", **pad
        )

        ttk.Label(tab, text="目标角色:").grid(row=2, column=0, sticky="e", **pad)
        self.character = tk.StringVar(value="")
        self.character_box = ttk.Combobox(
            tab, textvariable=self.character, values=[c["name"] for c in self.char_roster], width=20
        )
        self.character_box.grid(row=2, column=1, sticky="w", **pad)
        self.character_box.bind("<<ComboboxSelected>>", self._on_character_selected)
        self._register_action(ttk.Button(tab, text="重载名册", command=self.reload_characters)).grid(
            row=2, column=2, sticky="w", **pad
        )
        ttk.Label(tab, text="(留空=不自动选角)").grid(row=2, column=3, sticky="w", **pad)

        ttk.Label(tab, text="培养方向:").grid(row=2, column=4, sticky="e", **pad)
        self.build_profile = tk.StringVar(value="balanced")
        ttk.Combobox(
            tab, textvariable=self.build_profile, values=list(BUILD_PROFILES), width=16, state="readonly"
        ).grid(row=2, column=5, sticky="w", **pad)

        ttk.Label(tab, text="识别模式:").grid(row=3, column=0, sticky="e", **pad)
        self.mode_flag = tk.StringVar(value="--hybrid-mode")
        mode_frame = ttk.Frame(tab)
        mode_frame.grid(row=3, column=1, columnspan=5, sticky="w", **pad)
        for label, flag in CLASSIFY_MODES:
            ttk.Radiobutton(mode_frame, text=label, value=flag, variable=self.mode_flag).pack(side="left", padx=4)

        self.execute = tk.BooleanVar(value=False)
        self.verbose = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="执行点击 (取消=仅预演)", variable=self.execute).grid(
            row=4, column=1, columnspan=3, sticky="w", **pad
        )
        ttk.Checkbutton(tab, text="详细输出 (verbose)", variable=self.verbose).grid(
            row=4, column=4, columnspan=2, sticky="w", **pad
        )

        btns = ttk.Frame(tab)
        btns.grid(row=5, column=0, columnspan=6, sticky="w", **pad)
        self._register_action(ttk.Button(btns, text="▶ 启动循环", command=self.start_loop)).pack(side="left", padx=4)
        self._register_action(ttk.Button(btns, text="列出窗口", command=self.list_windows)).pack(side="left", padx=4)
        tab.columnconfigure(1, weight=1)

    # ------------------------------------------------------- tab: capture
    def _build_tab_capture(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb)
        nb.add(tab, text="截图 / 窗口")
        pad = {"padx": 6, "pady": 4}

        ttk.Label(tab, text="窗口标题:").grid(row=0, column=0, sticky="e", **pad)
        self.cap_window = tk.StringVar(value="StarSavior")
        ttk.Entry(tab, textvariable=self.cap_window, width=22).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(tab, text="输出文件:").grid(row=1, column=0, sticky="e", **pad)
        self.cap_out = tk.StringVar(value="screenshots/capture.png")
        ttk.Entry(tab, textvariable=self.cap_out, width=42).grid(row=1, column=1, columnspan=3, sticky="we", **pad)
        self._register_action(ttk.Button(tab, text="选择…", command=self._pick_capture_out)).grid(
            row=1, column=4, sticky="w", **pad
        )

        self.cap_timestamp = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="文件名追加时间戳", variable=self.cap_timestamp).grid(
            row=2, column=1, sticky="w", **pad
        )

        btns = ttk.Frame(tab)
        btns.grid(row=3, column=0, columnspan=5, sticky="w", **pad)
        self._register_action(ttk.Button(btns, text="截图", command=self.capture_once)).pack(side="left", padx=4)
        self._register_action(ttk.Button(btns, text="列出窗口", command=self.list_windows)).pack(side="left", padx=4)
        tab.columnconfigure(1, weight=1)

    # ----------------------------------------------------- tab: calibrate
    def _build_tab_calibrate(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb)
        nb.add(tab, text="区域标定 / OCR")
        pad = {"padx": 6, "pady": 4}

        ttk.Label(tab, text="截图:").grid(row=0, column=0, sticky="e", **pad)
        self.cal_image = tk.StringVar(value="")
        ttk.Entry(tab, textvariable=self.cal_image, width=42).grid(row=0, column=1, columnspan=3, sticky="we", **pad)
        self._register_action(ttk.Button(tab, text="选择…", command=self._pick_cal_image)).grid(
            row=0, column=4, sticky="w", **pad
        )

        ttk.Label(tab, text="区域配置:").grid(row=1, column=0, sticky="e", **pad)
        self.cal_profile = tk.StringVar(value=_default_profile(self.profiles))
        ttk.Combobox(tab, textvariable=self.cal_profile, values=self.profiles, width=42, state="readonly").grid(
            row=1, column=1, columnspan=3, sticky="we", **pad
        )

        # crop_regions
        crop = ttk.LabelFrame(tab, text="裁剪 + 叠加图 (crop_regions)")
        crop.grid(row=2, column=0, columnspan=5, sticky="we", **pad)
        ttk.Label(crop, text="裁剪输出目录:").grid(row=0, column=0, sticky="e", **pad)
        self.cal_outdir = tk.StringVar(value="debug/regions")
        ttk.Entry(crop, textvariable=self.cal_outdir, width=30).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(crop, text="叠加图:").grid(row=0, column=2, sticky="e", **pad)
        self.cal_overlay = tk.StringVar(value="debug/regions-overlay.png")
        ttk.Entry(crop, textvariable=self.cal_overlay, width=28).grid(row=0, column=3, sticky="w", **pad)
        self._register_action(ttk.Button(crop, text="生成裁剪/叠加图", command=self.crop_regions)).grid(
            row=1, column=0, columnspan=2, sticky="w", **pad
        )

        # read_regions
        ocr = ttk.LabelFrame(tab, text="区域 OCR (read_regions)")
        ocr.grid(row=3, column=0, columnspan=5, sticky="we", **pad)
        ttk.Label(ocr, text="引擎:").grid(row=0, column=0, sticky="e", **pad)
        self.ocr_engine = tk.StringVar(value="paddle")
        ttk.Combobox(ocr, textvariable=self.ocr_engine, values=["noop", "paddle"], width=8, state="readonly").grid(
            row=0, column=1, sticky="w", **pad
        )
        ttk.Label(ocr, text="前缀(空格分隔):").grid(row=0, column=2, sticky="e", **pad)
        self.ocr_prefix = tk.StringVar(value="character")
        ttk.Entry(ocr, textvariable=self.ocr_prefix, width=20).grid(row=0, column=3, sticky="w", **pad)
        self.ocr_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(ocr, text="全部区域 (慢)", variable=self.ocr_all).grid(row=1, column=1, sticky="w", **pad)
        self._register_action(ttk.Button(ocr, text="读取区域 OCR", command=self.read_regions)).grid(
            row=1, column=2, columnspan=2, sticky="w", **pad
        )

        tab.columnconfigure(1, weight=1)

    # ------------------------------------------------------- tab: offline
    def _build_tab_offline(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb)
        nb.add(tab, text="离线测试 / 回放")
        pad = {"padx": 6, "pady": 4}

        # offline_harness
        harness = ttk.LabelFrame(tab, text="离线决策 (offline_harness)")
        harness.grid(row=0, column=0, columnspan=5, sticky="we", **pad)

        self._register_action(ttk.Button(harness, text="运行内置 demo", command=self.harness_demo)).grid(
            row=0, column=0, sticky="w", **pad
        )

        ttk.Label(harness, text="manifest:").grid(row=1, column=0, sticky="e", **pad)
        self.harness_manifest = tk.StringVar(value="examples/demo_manifest.json")
        ttk.Entry(harness, textvariable=self.harness_manifest, width=38).grid(row=1, column=1, columnspan=2, sticky="we", **pad)
        self._register_action(ttk.Button(harness, text="选择…", command=self._pick_harness_manifest)).grid(
            row=1, column=3, sticky="w", **pad
        )
        self.harness_jsonl = tk.BooleanVar(value=False)
        ttk.Checkbutton(harness, text="JSONL 输出", variable=self.harness_jsonl).grid(row=1, column=4, sticky="w", **pad)
        self._register_action(ttk.Button(harness, text="运行 manifest", command=self.harness_run_manifest)).grid(
            row=2, column=1, sticky="w", **pad
        )

        ttk.Label(harness, text="截图目录:").grid(row=3, column=0, sticky="e", **pad)
        self.harness_screens = tk.StringVar(value="screenshots")
        ttk.Entry(harness, textvariable=self.harness_screens, width=38).grid(row=3, column=1, columnspan=2, sticky="we", **pad)
        self._register_action(ttk.Button(harness, text="按文件名分类目录", command=self.harness_screenshots)).grid(
            row=3, column=3, columnspan=2, sticky="w", **pad
        )
        harness.columnconfigure(1, weight=1)

        # run_manifest (real executor / clicks)
        replay = ttk.LabelFrame(tab, text="动作回放 (run_manifest)")
        replay.grid(row=1, column=0, columnspan=5, sticky="we", **pad)
        ttk.Label(replay, text="manifest:").grid(row=0, column=0, sticky="e", **pad)
        self.replay_manifest = tk.StringVar(value="examples/demo_manifest.json")
        ttk.Entry(replay, textvariable=self.replay_manifest, width=38).grid(row=0, column=1, columnspan=2, sticky="we", **pad)
        self._register_action(ttk.Button(replay, text="选择…", command=self._pick_replay_manifest)).grid(
            row=0, column=3, sticky="w", **pad
        )
        self.replay_execute = tk.BooleanVar(value=False)
        ttk.Checkbutton(replay, text="真实点击 (取消=预演)", variable=self.replay_execute).grid(
            row=1, column=1, sticky="w", **pad
        )
        self._register_action(ttk.Button(replay, text="回放动作", command=self.run_manifest)).grid(
            row=1, column=2, sticky="w", **pad
        )
        replay.columnconfigure(1, weight=1)

        tab.columnconfigure(0, weight=1)

    # --------------------------------------------------------- tab: tests
    def _build_tab_tests(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb)
        nb.add(tab, text="单元测试")
        pad = {"padx": 6, "pady": 6}
        ttk.Label(tab, text="运行 tests/ 下的全部单元测试。").grid(row=0, column=0, sticky="w", **pad)
        self.tests_verbose = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="详细 (-v)", variable=self.tests_verbose).grid(row=1, column=0, sticky="w", **pad)
        self._register_action(ttk.Button(tab, text="运行测试", command=self.run_tests)).grid(
            row=2, column=0, sticky="w", **pad
        )

    # ------------------------------------------------------- file pickers
    def _pick_capture_out(self) -> None:
        path = filedialog.asksaveasfilename(initialdir=str(SCREENSHOTS_DIR), defaultextension=".png")
        if path:
            self.cap_out.set(self._relativize(path))

    def _pick_cal_image(self) -> None:
        path = filedialog.askopenfilename(initialdir=str(SCREENSHOTS_DIR), filetypes=[("PNG", "*.png"), ("All", "*.*")])
        if path:
            self.cal_image.set(self._relativize(path))

    def _pick_harness_manifest(self) -> None:
        path = filedialog.askopenfilename(initialdir=str(EXAMPLES_DIR), filetypes=[("JSON", "*.json")])
        if path:
            self.harness_manifest.set(self._relativize(path))

    def _pick_replay_manifest(self) -> None:
        path = filedialog.askopenfilename(initialdir=str(EXAMPLES_DIR), filetypes=[("JSON", "*.json")])
        if path:
            self.replay_manifest.set(self._relativize(path))

    def _relativize(self, path: str) -> str:
        try:
            return str(Path(path).resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return path

    # ----------------------------------------------------------- plumbing
    def _python(self) -> str:
        return sys.executable or "python"

    def _base_cmd(self, *module_args: str) -> list[str]:
        return [self._python(), "-B", *module_args]

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll_log_queue(self) -> None:
        try:
            while True:
                self._append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _reader_thread(self, proc: subprocess.Popen[str], done_status: str) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self.log_queue.put(line)
        proc.wait()
        self.log_queue.put(f"\n[进程结束, 退出码 {proc.returncode}]\n")
        self.root.after(0, lambda: self._on_process_done(done_status))

    def _on_process_done(self, status: str) -> None:
        self.process = None
        for btn in self._action_buttons:
            btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status.set(status)

    def _spawn(self, cmd: list[str], status: str, done_status: str) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showwarning("忙碌中", "已有进程在运行, 请先停止。")
            return

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        self._append_log(f"\n$ {' '.join(cmd)}\n")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:  # pragma: no cover - defensive UI guard
            messagebox.showerror("启动失败", str(exc))
            return

        self.process = proc
        self.status.set(status)
        for btn in self._action_buttons:
            btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self._reader_thread, args=(proc, done_status), daemon=True).start()

    def stop_process(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.status.set("正在停止…")
        try:
            self.process.terminate()
        except Exception:
            pass

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------ actions
    def _on_character_selected(self, _event: object = None) -> None:
        """When a roster character is picked, auto-fill its recommended profile."""
        profile = self.char_profile_map.get(self.character.get().strip())
        if profile in BUILD_PROFILES:
            self.build_profile.set(profile)

    def reload_characters(self) -> None:
        self.char_roster = _load_characters()
        self.char_profile_map = {c["name"]: c["profile"] for c in self.char_roster}
        self.character_box.configure(values=[c["name"] for c in self.char_roster])
        self._append_log(f"\n[已重载角色名册: {len(self.char_roster)} 个角色]\n")

    def start_loop(self) -> None:
        if self.execute.get():
            if not messagebox.askyesno(
                "确认执行",
                "执行模式会真实点击鼠标控制游戏!\n请确认游戏窗口已就绪。\n\n继续?",
            ):
                return
        cmd = self._base_cmd(
            "-m", "starsavior_trainer.cli.live_loop",
            "--profile", self.live_profile.get(),
            "--window-title", self.window_title.get(),
            "--interval", self.interval.get(),
            "--max-iterations", self.max_iter.get(),
            "--build-profile", self.build_profile.get(),
        )
        if self.mode_flag.get():
            cmd.append(self.mode_flag.get())
        if self.execute.get():
            cmd.append("--execute")
        if self.verbose.get():
            cmd.append("--verbose")
        character = self.character.get().strip()
        if character:
            cmd.extend(["--character", character])
        label = "执行" if self.execute.get() else "预演"
        self._spawn(cmd, status=f"训练循环运行中 ({label})…", done_status="就绪")

    def list_windows(self) -> None:
        cmd = self._base_cmd("-m", "starsavior_trainer.cli.live_loop", "--list-windows")
        self._spawn(cmd, status="列出窗口…", done_status="就绪")

    def capture_once(self) -> None:
        cmd = self._base_cmd(
            "-m", "starsavior_trainer.cli.capture_once",
            "--window-title", self.cap_window.get(),
            "--out", self.cap_out.get(),
        )
        if self.cap_timestamp.get():
            cmd.append("--timestamp")
        self._spawn(cmd, status="截图中…", done_status="截图完成")

    def crop_regions(self) -> None:
        if not self.cal_image.get().strip():
            messagebox.showwarning("缺少截图", "请先选择一张截图。")
            return
        cmd = self._base_cmd(
            "-m", "starsavior_trainer.cli.crop_regions",
            "--image", self.cal_image.get(),
            "--profile", self.cal_profile.get(),
            "--out-dir", self.cal_outdir.get(),
            "--overlay", self.cal_overlay.get(),
        )
        self._spawn(cmd, status="生成裁剪/叠加图…", done_status="标定完成")

    def read_regions(self) -> None:
        if not self.cal_image.get().strip():
            messagebox.showwarning("缺少截图", "请先选择一张截图。")
            return
        cmd = self._base_cmd(
            "-m", "starsavior_trainer.cli.read_regions",
            "--image", self.cal_image.get(),
            "--profile", self.cal_profile.get(),
            "--engine", self.ocr_engine.get(),
        )
        if self.ocr_all.get():
            cmd.append("--all-regions")
        else:
            for prefix in self.ocr_prefix.get().split():
                cmd.extend(["--prefix", prefix])
        self._spawn(cmd, status="读取区域 OCR…", done_status="OCR 完成")

    def harness_demo(self) -> None:
        cmd = self._base_cmd("-m", "starsavior_trainer.cli.offline_harness", "--demo", "--jsonl")
        self._spawn(cmd, status="运行 demo…", done_status="完成")

    def harness_run_manifest(self) -> None:
        cmd = self._base_cmd(
            "-m", "starsavior_trainer.cli.offline_harness", "--manifest", self.harness_manifest.get()
        )
        if self.harness_jsonl.get():
            cmd.append("--jsonl")
        self._spawn(cmd, status="运行 manifest…", done_status="完成")

    def harness_screenshots(self) -> None:
        cmd = self._base_cmd(
            "-m", "starsavior_trainer.cli.offline_harness", "--screenshots", self.harness_screens.get()
        )
        self._spawn(cmd, status="分类截图目录…", done_status="完成")

    def run_manifest(self) -> None:
        if self.replay_execute.get():
            if not messagebox.askyesno("确认执行", "回放将真实点击鼠标!\n继续?"):
                return
        cmd = self._base_cmd("-m", "starsavior_trainer.cli.run_manifest", "--manifest", self.replay_manifest.get())
        if self.replay_execute.get():
            cmd.append("--execute-clicks")
        self._spawn(cmd, status="回放动作…", done_status="回放完成")

    def run_tests(self) -> None:
        cmd = self._base_cmd("-m", "unittest", "discover", "tests")
        if self.tests_verbose.get():
            cmd.append("-v")
        self._spawn(cmd, status="运行测试…", done_status="测试完成")


def main() -> None:
    root = tk.Tk()
    gui = TrainerGui(root)

    def on_close() -> None:
        if gui.process is not None and gui.process.poll() is None:
            if not messagebox.askyesno("退出", "进程仍在运行, 确定退出?"):
                return
            try:
                gui.process.terminate()
            except Exception:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
