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

call "%~dp0run_aurajobs.bat" --geo All --mode Deep --freshness 72
