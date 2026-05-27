@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Magic Creater World - Running

for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

echo %ESC%[96m[1m
echo   +==================================================+
echo   ^|         Magic Creater World                      ^|
echo   ^|         http://127.0.0.1:8765                   ^|
echo   +==================================================+
echo %ESC%[0m
echo.

:: ---- Step 1: Find Python interpreter -----------------------------
set "PYTHON_EXE="

:: 1) conda environment
if exist "E:\ananconda\envs\Agent\python.exe" (
    set "PYTHON_EXE=E:\ananconda\envs\Agent\python.exe"
    goto :check_env
)

:: 2) project .venv
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto :check_env
)

:: 3) Python user install (%%LOCALAPPDATA%%\Programs\Python)
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%d\python.exe" (
        set "PYTHON_EXE=%%d\python.exe"
        goto :check_env
    )
)

:: 4) Python system-wide install (Program Files)
for /d %%d in ("C:\Program Files\Python3*") do (
    if exist "%%d\python.exe" (
        set "PYTHON_EXE=%%d\python.exe"
        goto :check_env
    )
)

:: 5) Python on PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :check_env
)

echo   %ESC%[91m[X] Python not found%ESC%[0m
echo   Please run setup.bat first to configure your environment
echo.
pause
exit /b 1

:: ---- Step 2: Check .env ------------------------------------------
:check_env
if not exist ".env" (
    echo   %ESC%[93m[!] .env not found, creating from template...%ESC%[0m
    copy .env.example .env >nul
    echo   %ESC%[93m[!] Please edit .env and set PARATERA_API_KEY%ESC%[0m
    start notepad .env
    exit /b 1
)

for /f "tokens=1,2 delims==" %%a in ('findstr /b "PARATERA_API_KEY=" .env') do (
    set "KEY_VAL=%%b"
)
if "!KEY_VAL!"=="" (
    echo   %ESC%[93m[!] PARATERA_API_KEY is empty%ESC%[0m
    echo   Opening .env for editing...
    start notepad .env
    echo   After filling in the key, press any key to continue...
    pause >nul
)

:: ---- Step 3: Launch ----------------------------------------------
echo   %ESC%[92mStarting server...%ESC%[0m
echo   %ESC%[90mPress Ctrl+C to stop%ESC%[0m
echo.

"%PYTHON_EXE%" run.py %*

echo.
echo   %ESC%[90mServer stopped. Press any key to close...%ESC%[0m
pause >nul
endlocal
