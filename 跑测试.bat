@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 跑测试 (可移植: 自动定位仓库目录 + 自动找 Python, 台式机/笔记本通用)
cd /d "%~dp0"

REM ---- 探测 Python: Codex 运行时 > paddle 支持版(3.13~3.10) > PATH 兜底 ----
set "PY="
set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" set "PY="%CODEX_PY%""
if not defined PY ( py -3.13 --version >nul 2>nul && set "PY=py -3.13" )
if not defined PY ( py -3.12 --version >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 --version >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.10 --version >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY ( where python3 >nul 2>nul && set "PY=python3" )
if not defined PY (
    echo [错误] 没找到 Python, 请先运行 "准备环境.bat"
    pause
    exit /b 1
)

REM 只跑 tests/ 目录, 避免扫到 tools/ 里会触发真实 OCR 的调试脚本(慢且刷屏)
%PY% -B -m unittest discover -s tests -v
pause
