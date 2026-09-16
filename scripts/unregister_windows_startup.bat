@echo off
setlocal
title AuraJobs - Remove Windows Daily Auto-Runner
cd /d "%~dp0"

echo ============================================================
echo   AURAJOBS - REMOVE AUTO-RUNNER
echo ============================================================
echo.

set "STARTUP_TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AuraJobs_AutoRunner.vbs"

echo [*] Removing background runner from Windows Startup...
if exist "%STARTUP_TARGET%" (
    del /f /q "%STARTUP_TARGET%" >nul 2>&1
    echo [OK] Removed from Windows Startup folder.
)

schtasks /delete /tn "AuraJobs_Daily_Discovery" /f >nul 2>&1

echo.
echo [SUCCESS] Scheduled auto-runner has been disabled successfully.
echo.
pause
