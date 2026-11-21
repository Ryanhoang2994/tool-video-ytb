@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat call install_windows.bat
call .venv\Scripts\activate.bat
echo === Viet kich ban hang loat (batch\queue.yaml). Dung: Ctrl+C - chay lai se tiep tuc cho do ===
python batch.py %*
pause
