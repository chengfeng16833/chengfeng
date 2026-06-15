@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 跑测试 (可移植: 自动定位仓库目录 + 自动找 Python, 台式机/笔记本通用)
cd /d "%~dp0"

REM ---- 探测 Python: 先用 Codex 自带运行时(台式机), 再回退 PATH ----
set "PY="
set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" set "PY="%CODEX_PY%""
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    where python3 >nul 2>nul && set "PY=python3"
)
if not defined PY (
    echo [错误] 没找到 Python, 请先安装 Python 3.11+ 并勾选 "Add to PATH"
    pause
    exit /b 1
)

REM 只跑 tests/ 目录, 避免扫到 tools/ 里会触发真实 OCR 的调试脚本(慢且刷屏)
%PY% -B -m unittest discover -s tests -v
pause
