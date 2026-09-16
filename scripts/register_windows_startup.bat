@echo off
setlocal
title AuraJobs - Setup Windows Daily Auto-Runner
cd /d "%~dp0"

echo ============================================================
echo   AURAJOBS - WINDOWS DAILY AUTO-RUNNER INSTALLER
echo ============================================================
echo.
echo This utility configures AuraJobs to run silently in the background
echo every time you turn on your computer and log in, automatically
echo searching for fresh jobs and sending alerts to your Telegram.
echo.

set "SCRIPT_DIR=%~dp0"
set "VBS_SOURCE=%SCRIPT_DIR%run_headless_daily.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_TARGET=%STARTUP_FOLDER%\AuraJobs_AutoRunner.vbs"

if not exist "%VBS_SOURCE%" (
    echo [ERROR] Could not find %VBS_SOURCE%
    pause
    exit /b 1
)

echo [*] Installing silent background runner into Windows Startup...
copy /Y "%VBS_SOURCE%" "%STARTUP_TARGET%" >nul

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo   [SUCCESS] AuraJobs Auto-Runner Configured Successfully!
    echo ============================================================
    echo - AuraJobs will run silently in the background whenever you log into Windows.
    echo - Alerts will be delivered directly to your Telegram bot.
    echo - No Administrator rights were needed.
    echo - To disable auto-run at any time, run 'unregister_windows_startup.bat'.
    echo.
) else (
    echo [ERROR] Failed to copy runner to Startup folder: %STARTUP_FOLDER%
)

pause
