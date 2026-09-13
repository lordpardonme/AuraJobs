@echo off
chcp 65001 >nul
title AuraJobs - Autonomous Career Intelligence Engine
cd /d "%~dp0"

echo ============================================================
echo   AURAJOBS - AUTONOMOUS CAREER INTELLIGENCE ENGINE
echo ============================================================
echo.
echo Working Directory: %~dp0
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in your PATH.
    echo Please install Python or ensure it is accessible.
    echo.
    pause
    exit /b 1
)

python -c "import pandas, yaml, jobspy" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Missing required dependencies.
    echo Please ensure python-jobspy, pandas, and pyyaml are installed.
    echo.
    pause
    exit /b 1
)

echo [OK] Python and dependencies loaded.
echo.
echo Launching AuraJobs engine...
echo.

python main.py

echo.
echo ============================================================
echo EXECUTION COMPLETED
echo ============================================================
pause
