@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Cold Case Studio - cai dat
echo ============================================
echo.

rem ---- 1. Python: uu tien 3.12 (ban moi qua nhu 3.14/3.15 nhieu thu vien chua ho tro) ----
set "PY="
py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3.11 -c "import sys" >nul 2>nul && set "PY=py -3.11"
if not defined PY py -3.13 -c "import sys" >nul 2>nul && set "PY=py -3.13"
if defined PY goto pyok
where py >nul 2>nul
if errorlevel 1 goto trypython
echo [..] Dang cai Python 3.12 (neu duoc hoi, go Y roi Enter)...
py install 3.12
py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12"
if defined PY goto pyok
:trypython
python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto nopython
:pyok
for /f "delims=" %%v in ('%PY% --version') do echo [OK] %%v

rem ---- 2. ffmpeg ----
where ffmpeg >nul 2>nul
if errorlevel 1 goto getffmpeg
echo [OK] ffmpeg
goto venv
:getffmpeg
echo [..] Chua co ffmpeg - dang cai bang winget...
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
set "NEWFF=1"

:venv
rem ---- 3. Moi truong Python rieng (.venv) ----
if not exist .venv\Scripts\python.exe (
  echo [..] Tao moi truong .venv ...
  %PY% -m venv .venv
)
if not exist .venv\Scripts\python.exe goto venverr
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul

rem ---- 4. Thu vien ----
echo [..] Cai thu vien (lan dau co the mat 5-15 phut)...
pip install -r requirements.txt
if not errorlevel 1 goto envfile
echo.
echo [!] Cai chung bi loi - thu cai tung thu vien mot...
set "FAILED="
for /f "usebackq tokens=1" %%p in ("requirements.txt") do call :one %%p
if defined FAILED echo [!] Khong cai duoc:%FAILED%  - cac chuc nang khac van chay. Chup man hinh gui lai neu can.

:envfile
if not exist .env copy .env.example .env >nul
echo.
echo ============================================
echo   XONG! Bam dup start_ui.bat de mo giao dien.
echo ============================================
if defined NEWFF echo (Vua cai ffmpeg: tat het cua so cmd roi moi bam start_ui.bat)
pause
exit /b

:one
set "PK=%~1"
if "%PK:~0,1%"=="#" exit /b
pip install "%PK%" >nul 2>nul
if errorlevel 1 (
  echo     loi: %PK%
  set "FAILED=%FAILED% %PK%"
) else (
  echo     ok: %PK%
)
exit /b

:nopython
echo [!] Chua co Python 3.10 - 3.13 (hoac chua tick "Add python.exe to PATH").
echo.
echo     1. Tai Python 3.12 o trang vua mo (keo xuong muc "Looking for a specific release", chon 3.12.x)
echo     2. Khi cai, nho TICK o "Add python.exe to PATH" o man hinh dau tien
echo     3. Cai xong, TAT cua so nay, mo cua so cmd MOI roi chay lai install_windows.bat
start "" https://www.python.org/downloads/
pause
exit /b

:oldpython
echo [!] Python qua cu - can ban 3.10 tro len (khuyen dung 3.12).
start "" https://www.python.org/downloads/
pause
exit /b

:venverr
echo [!] Khong tao duoc moi truong .venv - chup man hinh gui lai de duoc ho tro.
pause
exit /b
