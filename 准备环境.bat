@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM  一键准备环境 (台式机/笔记本通用)
REM  - 自动定位本仓库目录(脚本所在目录), 无需手改路径
REM  - 自动探测 Python: 优先 paddle 支持的 3.13/3.12/3.11, 避开 3.14
REM  - 校验版本(必须 3.9~3.13, 否则直接提示, 不白装)
REM  - 安装 requirements.txt (优先清华镜像, 失败回退官方源)
REM  - 跑单元测试确认环境就绪
REM ============================================================

cd /d "%~dp0"
echo [信息] 仓库目录: %cd%
echo.

REM ---- 探测 Python ----
set "PY="
REM 台式机: Codex 自带运行时优先
set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" set "PY="%CODEX_PY%""
REM 笔记本: 优先挑 paddle 支持的版本(3.13~3.10), 避开过新的 3.14
if not defined PY ( py -3.13 --version >nul 2>nul && set "PY=py -3.13" )
if not defined PY ( py -3.12 --version >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 --version >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.10 --version >nul 2>nul && set "PY=py -3.10" )
REM 兜底: PATH 上的 python
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY ( where python3 >nul 2>nul && set "PY=python3" )
if not defined PY (
    echo [错误] 没找到 Python, 请先安装 Python 3.13 并勾选 "Add to PATH"
    echo        下载: https://www.python.org/downloads/  (选 3.13.x, 不要 3.14)
    pause
    exit /b 1
)
echo [信息] 使用 Python: %PY%
%PY% --version
echo.

REM ---- 校验版本: 依赖 paddlepaddle 只支持到 3.13 ----
%PY% -c "import sys;raise SystemExit(0 if (3,9)<=sys.version_info[:2]<=(3,13) else 1)"
if errorlevel 1 (
    echo.
    echo [错误] 当前 Python 版本不被依赖支持!
    echo        paddlepaddle 3.2.2 只支持 Python 3.9 ~ 3.13, 没有 3.14 的安装包。
    echo        请安装 Python 3.13.x: https://www.python.org/downloads/
    echo        安装后重新双击本脚本即可(它会自动优先用 3.13)。
    pause
    exit /b 1
)

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
        echo [错误] 依赖安装失败, 请检查网络后重试, 或把报错发我
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
