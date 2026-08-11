@echo off
timeout /t 30 /nobreak
cd /d C:\Users\ProfitTrailer\bitcoin-bot
call venv\Scripts\activate.bat
start python dashboard.py
python paper_trade.py
pause