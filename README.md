# Starsavior Trainer

PC version automation design for a Starsavior training script.

The first target is a single-screen recognizer and decision loop:

1. Capture the current game window.
2. Classify the current screen state.
3. Extract OCR/CV observations from fixed regions.
4. Score the available actions.
5. Click the safest selected target.

See [docs/starsavior-trainer-design.md](docs/starsavior-trainer-design.md) for the architecture and rule model.
See [docs/screenshot-collection.md](docs/screenshot-collection.md) for the screenshots needed to calibrate real OCR and click regions.

## 全局控制台 GUI (鼠标操作)

双击根目录的 `启动控制台.bat`, 或运行:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.gui
```

一个分页式控制台, 把项目全部 CLI 功能集成到一个窗口, 共享一块实时日志:

- **训练循环** — 设置窗口标题/间隔/轮次/区域配置/目标角色/培养方向/识别模式, 启动循环 + 列出窗口。默认预演, 勾 "执行点击" 才真实操作 (二次确认)。目标角色是一个下拉框, 从 `config/characters.json` 名册读取, 选中角色会自动带出其推荐培养方向; 也可手输自定义名字, 改完名册点 "重载名册" 即可刷新。脚本会在游戏角色选择画面自动滚动找到并选中该角色后开跑。
- **截图 / 窗口** — 抓取游戏窗口截图 (可加时间戳)、列出可见窗口。
- **区域标定 / OCR** — `crop_regions` 生成裁剪图与叠加图; `read_regions` 按前缀/全部区域跑 OCR。
- **离线测试 / 回放** — `offline_harness` 跑内置 demo / manifest / 截图目录; `run_manifest` 回放动作 (可真实点击)。
- **单元测试** — 一键运行 `tests/`。

底部有全局 "停止当前进程 / 清空日志" 按钮和状态栏。同一时刻只运行一个子进程。

## 项目结构

- `starsavior_trainer/` — 主包 (models, policy, screen_reader, classifier, vision, cli/)
- `tests/` — 单元测试 (`python -m unittest discover tests`)
- `config/regions/` — 各分辨率的区域坐标
- `docs/` — 设计文档与事件数据库
- `tools/` — 一次性调试/诊断脚本 (`_*.py`, `_*.bat`), 非主流程

## Prototype

The current prototype is intentionally throwaway logic code. It does not capture the screen or click the game.

Run:

```powershell
python .\prototypes\decision_loop.py
```

If Python is not on PATH inside Codex, use the bundled runtime:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\prototypes\decision_loop.py
```

It prints several simulated screen observations and the action the trainer would choose.

## Offline Harness

Run built-in observations through the real policy package:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.offline_harness --demo --profile .\config\regions\1920x1080.json
```

Run a labeled manifest:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.offline_harness --manifest .\examples\demo_manifest.json --jsonl
```

Later, saved screenshots can be placed in a directory and named with screen states such as `training_select_001.png` for temporary filename classification:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.offline_harness --screenshots .\screenshots
```

## Screenshot Tools

List visible windows:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.capture_once --list-windows
```

Capture the Starsavior window:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.capture_once --window-title Starsavior --out .\screenshots\starsavior.png --timestamp
```

Crop configured regions and draw an overlay for coordinate checking:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.crop_regions --image .\screenshots\starsavior.png --profile .\config\regions\1920x1080.json
```

For the first provided windowed screenshot, use the `2048x1190` profile:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.crop_regions --image .\screenshots\initial_001.png --profile .\config\regions\2048x1190.json
```

Read region OCR. Use `--engine noop` for plumbing checks and `--engine paddle` once you want to run PaddleOCR:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.read_regions --image .\screenshots\starsavior.png --engine noop
```

## Click Execution

Run manifest decisions through the click executor in dry-run mode:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.run_manifest --manifest .\examples\demo_manifest.json
```

Only use real clicking after the screenshot regions are verified:

```powershell
& 'C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m starsavior_trainer.cli.run_manifest --manifest .\examples\demo_manifest.json --execute-clicks
```
