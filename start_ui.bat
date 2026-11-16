@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat goto run
echo Lan dau mo: dang cai dat truoc...
echo.
call install_windows.bat
if not exist .venv\Scripts\activate.bat (
  echo.
  echo [!] Chua cai dat xong - xem thong bao o tren, lam theo roi bam dup start_ui.bat lai.
  pause
  exit /b
)
:run
call .venv\Scripts\activate.bat
python studio.py ui
pause
