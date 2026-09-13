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
    echo [ERROR] Python was not found in your PATH.
    echo Please install Python 3.10+ and add it to your system PATH.
    echo.
    pause
    exit /b 1
)

python -c "import pandas, yaml, jobspy" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Missing required Python packages.
    echo Running automatic dependency installation...
    echo.
    python -m pip install pandas pyyaml python-jobspy requests
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo [OK] Python and all core adapters ready.
echo.
echo Launching AuraJobs interactive engine...
echo.

python main.py

echo.
echo ============================================================
echo   AURAJOBS RUN COMPLETE
echo ============================================================
pause
