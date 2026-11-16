@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Cap nhat Cold Case Studio tu GitHub ===
git pull --ff-only || (echo Loi git pull. Thu muc nay co the tai bang ZIP - hay cai lai bang git clone. & pause & exit /b)
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
echo.
echo Xong! Bam dup start_ui.bat de mo giao dien.
pause
