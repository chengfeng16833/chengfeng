@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 笔记本版跑测试 (不写死路径, 自动找 Python)
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    where python3 >nul 2>nul && set "PY=python3"
)
if not defined PY (
    echo [错误] 没找到 Python, 请先运行 "笔记本-准备环境.bat"
    pause
    exit /b 1
)

REM 只跑 tests/ 目录, 避免扫到 tools/ 里会触发真实 OCR 的调试脚本
%PY% -B -m unittest discover -s tests -v
pause
