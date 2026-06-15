@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM  一键准备环境 (台式机/笔记本通用)
REM  - 自动定位本仓库目录(脚本所在目录), 无需手改路径
REM  - 自动探测 Python (先 Codex 自带运行时, 再回退 PATH)
REM  - 安装 requirements.txt (优先清华镜像, 失败回退官方源)
REM  - 跑单元测试确认环境就绪
REM ============================================================

cd /d "%~dp0"
echo [信息] 仓库目录: %cd%
echo.

REM ---- 探测 Python ----
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
    echo        下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [信息] 使用 Python: %PY%
%PY% --version
echo.

REM ---- 升级 pip ----
echo [步骤 1/3] 升级 pip ...
%PY% -m pip install --upgrade pip
echo.

REM ---- 安装依赖 ----
echo [步骤 2/3] 安装依赖 (清华镜像) ...
%PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo [警告] 清华镜像失败, 改用官方源重试 ...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败, 请检查网络后重试
        pause
        exit /b 1
    )
)
echo.

REM ---- 跑测试 ----
echo [步骤 3/3] 跑单元测试 (确认环境就绪) ...
%PY% -B -m unittest discover -s tests
if errorlevel 1 (
    echo.
    echo [结果] 测试有失败, 环境可能未完全就绪, 请把上面的报错发我
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  [完成] 全部测试通过, 环境就绪!
echo  下一步: 双击 "启动控制台.bat" 打开 GUI
echo ============================================================
pause
