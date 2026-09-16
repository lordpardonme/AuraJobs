@echo off
chcp 65001 >nul
title AuraJobs - Autonomous Career Intelligence Engine
cd /d "%~dp0"

call "%~dp0run_aurajobs.bat" %*
