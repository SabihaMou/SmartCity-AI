@echo off
setlocal
cd /d "%~dp0"
title SmartCity AI - Traffic Intelligence Lab
where py >nul 2>&1
if %errorlevel%==0 (
  py -3.10 -c "import sys" >nul 2>&1
  if %errorlevel%==0 (set "PY=py -3.10") else (set "PY=py -3")
) else (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
 echo Creating virtual environment...
 %PY% -m venv .venv
 if errorlevel 1 goto fail
)
set "VENV_PY=.venv\Scripts\python.exe"
"%VENV_PY%" -c "import pygame" >nul 2>&1
if errorlevel 1 (
 echo Installing Pygame (internet required for first run)...
 "%VENV_PY%" -m pip install -r requirements.txt
 if errorlevel 1 goto fail
)
echo Launching SmartCity AI...
"%VENV_PY%" main.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo Could not launch. Install Python 3.10 from python.org, enable PATH, and retry.
pause
exit /b 1
