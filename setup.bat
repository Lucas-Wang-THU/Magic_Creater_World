@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Magic Creater World - Setup

for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

echo %ESC%[96m[1m
echo   +==================================================+
echo   ^|         Magic Creater World                      ^|
echo   ^|         One-Click Environment Setup              ^|
echo   +==================================================+
echo %ESC%[0m
echo.

:: ---- Step 1: Detect Python ---------------------------------------
echo %ESC%[96m[1/6] Detecting Python...%ESC%[0m

set "PYTHON_EXE="
set "USE_CONDA=0"

if exist "E:nanconda\envs\Agent\python.exe" (
    set "PYTHON_EXE=E:nanconda\envs\Agent\python.exe"
    set "USE_CONDA=1"
    echo   %ESC%[92m[OK] Found conda environment%ESC%[0m
    goto :check_python_version
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%i"
    echo   %ESC%[92m[OK] Found system Python%ESC%[0m
    goto :check_python_version
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('py -3.10 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
    if defined PYTHON_EXE (
        echo   %ESC%[92m[OK] Found Python (py launcher)%ESC%[0m
        goto :check_python_version
    )
)

echo   %ESC%[91m[X] Python 3.10+ not found%ESC%[0m
echo.
echo   Please install Python 3.10 or later:
echo   https://www.python.org/downloads/
echo   (Check "Add Python to PATH" during installation)
echo.
pause
exit /b 1

:check_python_version
for /f "tokens=2 delims= " %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do set "PY_VER=%%v"
echo   %ESC%[92m   Version: !PY_VER!%ESC%[0m
echo.

:: ---- Step 2: Prepare Python environment --------------------------
echo %ESC%[96m[2/6] Preparing Python environment...%ESC%[0m

if "%USE_CONDA%"=="1" (
    echo   %ESC%[92m[OK] Using conda environment%ESC%[0m
    goto :install_deps
)

if defined VIRTUAL_ENV (
    echo   %ESC%[92m[OK] Already in virtual environment%ESC%[0m
    goto :install_deps
)

if not exist ".venv\Scripts\python.exe" (
    echo   Creating virtual environment .venv ...
    "%PYTHON_EXE%" -m venv .venv
    if %errorlevel% neq 0 (
        echo   %ESC%[91m[X] Failed to create virtual environment%ESC%[0m
        pause
        exit /b 1
    )
    echo   %ESC%[92m[OK] Virtual environment created%ESC%[0m
) else (
    echo   %ESC%[92m[OK] Virtual environment exists%ESC%[0m
)
set "PYTHON_EXE=.venv\Scripts\python.exe"
echo.

:: ---- Step 3: Install dependencies --------------------------------
echo %ESC%[96m[3/6] Installing Python dependencies...%ESC%[0m
echo   (This may take a few minutes)
echo.

"%PYTHON_EXE%" -m pip install --upgrade pip --quiet 2>nul

"%PYTHON_EXE%" -m pip install -r requirements.txt --default-timeout=120 2>nul
if %errorlevel% neq 0 (
    echo   %ESC%[93m[!] Default index slow, retrying with mirror...%ESC%[0m
    "%PYTHON_EXE%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=120
    if %errorlevel% neq 0 (
        echo   %ESC%[91m[X] Dependency installation failed%ESC%[0m
        echo   Please check your network connection and try again.
        pause
        exit /b 1
    )
)
echo   %ESC%[92m[OK] Dependencies installed%ESC%[0m
echo.

:: ---- Step 4: Configure .env --------------------------------------
echo %ESC%[96m[4/6] Configuring .env...%ESC%[0m

if exist ".env" (
    echo   %ESC%[92m[OK] .env already exists%ESC%[0m
) else (
    copy .env.example .env >nul
    echo   %ESC%[92m[OK] Created .env from template%ESC%[0m
    echo.
    echo   %ESC%[93m[!] Please set your API Key:%ESC%[0m
    echo       Edit .env and fill in PARATERA_API_KEY=
    echo.
    choice /c yn /n /m "    Open .env in Notepad now? [Y/N] "
    if !errorlevel! equ 1 (
        start notepad .env
        echo    Close Notepad when done, then press any key...
        pause >nul
    )
)
echo.

:: ---- Step 5: Generate brand icon ---------------------------------
echo %ESC%[96m[5/6] Generating brand icon...%ESC%[0m
"%PYTHON_EXE%" -c "
import struct, os
OUT = 'icon.ico'
SIZE = 32
BG_R, BG_G, BG_B = 15, 118, 110
FG_R, FG_G, FG_B = 255, 255, 255
pixels = []
for y in range(SIZE):
    row = []
    for x in range(SIZE):
        mx = x - 5
        my = y - 6
        mw = 22
        mh = 20
        inside = False
        if 0 <= mx < mw and 0 <= my < mh:
            if mx <= 3:
                inside = True
            elif mx >= mw - 4:
                inside = True
            elif 4 <= mx <= mw // 2:
                diag_y = int(mh - (mx - 4) * mh / (mw // 2 - 3))
                if my >= diag_y:
                    inside = True
            elif mw // 2 < mx <= mw - 5:
                diag_y = int(mh - (mw - 5 - mx) * mh / (mw // 2 - 3))
                if my >= diag_y:
                    inside = True
        if 14 <= x <= 17 and 2 <= y <= 4:
            inside = True
        if 12 <= x <= 19 and 3 <= y <= 3:
            inside = True
        if 15 <= x <= 15 and 1 <= y <= 5:
            inside = True
        if inside:
            row.append((FG_B, FG_G, FG_R, 255))
        else:
            row.append((BG_B, BG_G, BG_R, 255))
    pixels.append(row)
bmp_pixels = b''
for row in reversed(pixels):
    for (b, g, r, a) in row:
        bmp_pixels += struct.pack('BBBB', b, g, r, a)
dib = struct.pack('<IiiHHIIiiII', 40, SIZE, SIZE * 2, 1, 32, 0,
    len(bmp_pixels) + SIZE * SIZE // 8, 0, 0, 0, 0)
and_mask = b'\x00' * (SIZE * SIZE // 8)
bm_data = dib + bmp_pixels + and_mask
ico_header = struct.pack('<HHH', 0, 1, 1)
ico_entry = struct.pack('<BBBBHHII', SIZE, SIZE, 0, 0, 1, 32, len(bm_data), 22)
with open(OUT, 'wb') as f:
    f.write(ico_header + ico_entry + bm_data)
print('  [OK] icon.ico generated')
"
if %errorlevel% neq 0 (
    echo   %ESC%[93m[!] Icon generation failed (non-critical), skipped%ESC%[0m
) else (
    echo   %ESC%[92m[OK] Brand icon generated: icon.ico%ESC%[0m
)
echo.

:: ---- Step 6: Verify -----------------------------------------------
echo %ESC%[96m[6/6] Verifying installation...%ESC%[0m
"%PYTHON_EXE%" -m pytest tests/ -q --tb=line --no-header -k "not test_format_proofreader" 2>nul
if %errorlevel% equ 0 (
    echo   %ESC%[92m[OK] All tests passed - Environment ready!%ESC%[0m
) else (
    echo   %ESC%[93m[!] Some tests failed (may be network/API Key related)%ESC%[0m
)
echo.

echo %ESC%[92m[1m
echo   +==================================================+
echo   ^|         Setup Complete!                          ^|
echo   ^|                                                  ^|
echo   ^|  To start:                                       ^|
echo   ^|    Double-click launch.bat                       ^|
echo   ^|    Or: .venv\Scripts\python run.py              ^|
echo   ^|                                                  ^|
echo   ^|  Desktop shortcut (optional):                    ^|
echo   ^|    Right-click launch.bat ^> Send to desktop      ^|
echo   ^|    Right-click shortcut ^> Properties             ^|
echo   ^|    ^> Change Icon ^> select icon.ico              ^|
echo   +==================================================+
echo %ESC%[0m

pause
endlocal
