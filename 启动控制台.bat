@echo off
chcp 65001 >nul
cd /d C:\Users\ChengFeng\Desktop\starsavior-trainer
start "" C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m starsavior_trainer.cli.gui
