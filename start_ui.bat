@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Chua cai dat. Chay install_windows.bat truoc.
  pause
  exit /b
)
call .venv\Scripts\activate.bat
python studio.py ui
pause
