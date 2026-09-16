@echo off
REM ============================================================
REM AuraJobs Daily Alerts - Windows Launcher
REM ============================================================
REM Starts the alert daemon with proper environment setup.
REM Ensure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in
REM System Environment Variables or user profile before running.
REM ============================================================

chcp 65001 >nul
title AuraJobs Daily Alerts Daemon

echo.
echo ============================================================
echo   AURAJOBS DAILY ALERTS - DAEMON LAUNCHER
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

REM Check if we're in the right directory
if not exist "alerts.py" (
    echo [ERROR] alerts.py not found in current directory.
    echo Please run this script from the AuraJobs project root.
    pause
    exit /b 1
)

REM Check for virtual environment
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo [WARN] No virtual environment found. Using system Python.
)

REM Verify dependencies
python -c "import apscheduler, pydantic, requests, yaml, pandas" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Missing dependencies. Run: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Check for required environment variables
if not defined TELEGRAM_BOT_TOKEN (
    echo [WARN] TELEGRAM_BOT_TOKEN not set in environment.
    echo Set it in System Environment Variables or run:
    echo   setx TELEGRAM_BOT_TOKEN "your_bot_token_here"
    echo   setx TELEGRAM_CHAT_ID "your_chat_id_here"
    echo.
    echo You can also run 'python alerts.py --setup' to configure interactively.
    echo.
)

if not defined TELEGRAM_CHAT_ID (
    echo [WARN] TELEGRAM_CHAT_ID not set in environment.
    echo.
)

echo.
echo Starting AuraJobs Alert Daemon...
echo Press Ctrl+C to stop.
echo ============================================================
echo.

python alerts.py --daemon

echo.
echo Daemon stopped.
pause