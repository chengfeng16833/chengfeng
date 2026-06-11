@echo off
chcp 65001 >nul
cd /d C:\Users\ChengFeng\Desktop\starsavior-trainer
REM 限定 tests/ 目录：避免扫描 tools/ 里的调试脚本(会触发真实OCR、慢且刷屏)
REM 2026-06-11: 捆绑 Python 里 pytest 已不在(运行时被更新过), 改用自带的 unittest, 效果相同
set PYTHONUTF8=1
C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest discover -s tests
pause
