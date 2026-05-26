@echo off
chcp 65001 >nul
cd /d C:\Users\ChengFeng\Desktop\starsavior-trainer
REM 限定 tests/ 目录：避免 pytest 扫描 tools/ 里的调试脚本(会触发真实OCR、慢且刷屏)
C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m pytest tests/ -v
pause
