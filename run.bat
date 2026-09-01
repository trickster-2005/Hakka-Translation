@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo [!] 找不到 .venv，請先執行： py -3.11 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
.venv\Scripts\python.exe bot.py
pause
