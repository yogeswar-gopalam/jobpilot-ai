@echo off
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Edit .env and add your API keys for live jobs and live AI chat.
echo Starting JobPilot AI at http://127.0.0.1:5000
python app.py
pause
