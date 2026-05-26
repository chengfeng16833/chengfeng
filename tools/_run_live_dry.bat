@echo off
cd /d C:\Users\ChengFeng\Desktop\starsavior-trainer
C:\Users\ChengFeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m starsavior_trainer.cli.live_loop --profile config\regions\2560x1440.json --window-title StarSavior --hybrid-mode --interval 2 --verbose
