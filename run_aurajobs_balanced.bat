@echo off
chcp 65001 >nul
title AuraJobs - Balanced Multi-Region Search
cd /d "%~dp0"

echo ============================================================
echo   AURAJOBS - BALANCED MULTI-REGION CAREER ENGINE
echo ============================================================
echo.
echo Regions     : India (45%%) + Middle East (30%%) + Global (25%%)
echo Freshness   : 72-Hour posting window
echo Deduplication & Match Scoring Enabled
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

echo Starting AuraJobs Engine in Balanced Deep Mode...
echo.

python main.py --geo All --mode Deep --freshness 72

echo.
echo ============================================================
echo   AURAJOBS RUN COMPLETE
echo ============================================================
pause
