@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AuraJobs - Autonomous Career Intelligence Engine
cd /d "%~dp0"

echo ============================================================
echo   AURAJOBS - AUTONOMOUS CAREER INTELLIGENCE ENGINE
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "RUNTIME_DIR=%SCRIPT_DIR%.runtime"
set "PYTHON_EXE="

:: ---------------------------------------------------------
:: 1. Check for Local Portable Runtime in .runtime\
:: ---------------------------------------------------------
if exist "%RUNTIME_DIR%\python.exe" (
    "%RUNTIME_DIR%\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=%RUNTIME_DIR%\python.exe"
        echo [INFO] Using portable local Python runtime: .runtime\python.exe
        goto :python_found
    )
)

:: ---------------------------------------------------------
:: 2. Check Windows Python Launcher (py -3)
:: ---------------------------------------------------------
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=py -3"
        echo [INFO] Using Windows Python Launcher (py -3)
        goto :python_found
    )
)

:: ---------------------------------------------------------
:: 3. Check System PATH (python)
:: ---------------------------------------------------------
where python >nul 2>&1
if %errorlevel% equ 0 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
        echo [INFO] Using system PATH Python
        goto :python_found
    )
)

:: ---------------------------------------------------------
:: 4. Search Common Installation Paths (AppData, Program Files, Conda)
:: ---------------------------------------------------------
for %%P in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Program Files\Python310\python.exe"
    "%UserProfile%\anaconda3\python.exe"
    "%UserProfile%\miniconda3\python.exe"
    "%UserProfile%\miniforge3\python.exe"
    "C:\ProgramData\anaconda3\python.exe"
    "C:\ProgramData\miniconda3\python.exe"
) do (
    if exist "%%~P" (
        "%%~P" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=%%~P"
            echo [INFO] Found installed Python: %%~P
            goto :python_found
        )
    )
)

:: ---------------------------------------------------------
:: 5. Auto-Provision Portable Python Runtime (Zero-Install)
:: ---------------------------------------------------------
echo [!] No Python 3.10+ installation detected in PATH or standard directories.
echo [+] Auto-provisioning self-contained portable Python environment into .runtime\...
echo.

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

echo [*] Downloading portable Python runtime (one-time setup)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference = 'SilentlyContinue';" ^
    "$url = 'https://github.com/astral-sh/python-build-standalone/releases/download/20240814/cpython-3.11.9+20240814-x86_64-pc-windows-msvc-install_only.tar.gz';" ^
    "$dest = Join-Path $env:TEMP 'portable_python.tar.gz';" ^
    "Invoke-WebRequest -Uri $url -OutFile $dest;" ^
    "tar -xzf $dest -C '%RUNTIME_DIR%' --strip-components=1;" ^
    "Remove-Item -Force $dest;"

if exist "%RUNTIME_DIR%\python.exe" (
    set "PYTHON_EXE=%RUNTIME_DIR%\python.exe"
    echo [OK] Portable Python runtime installed successfully!
    echo.
) else (
    echo [ERROR] Failed to auto-provision portable Python.
    echo Please install Python 3.10+ from https://www.python.org and ensure "Add Python to PATH" is checked.
    pause
    exit /b 1
)

:python_found
echo.
echo [*] Checking dependencies...
%PYTHON_EXE% -c "import pandas, yaml, jobspy, requests, tabulate, scrapling, patchright" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Missing required packages. Installing project dependencies...
    %PYTHON_EXE% -m pip install --upgrade pip >nul 2>&1
    %PYTHON_EXE% -m pip install -r "%SCRIPT_DIR%requirements.txt"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed successfully.
) else (
    echo [OK] All dependencies ready.
)

echo.
echo ============================================================
echo   LAUNCHING AURAJOBS ENGINE
echo ============================================================
echo.

%PYTHON_EXE% "%SCRIPT_DIR%main.py" %*

echo.
echo ============================================================
echo   AURAJOBS RUN COMPLETE
echo ============================================================
pause
