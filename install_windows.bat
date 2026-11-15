@echo off
chcp 65001 >nul
echo === Cold Case Studio - cai dat ===
where python >nul 2>nul || (echo Can cai Python 3.10+ tu python.org (tick "Add to PATH") & pause & exit /b)
where ffmpeg >nul 2>nul || (echo Dang cai ffmpeg... & winget install --id Gyan.FFmpeg -e)
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Xong! Mo file .env de dien API key, sua config.yaml (capcut.drafts_dir).
echo Moi lan dung: .venv\Scripts\activate.bat  roi  python studio.py --help
pause
