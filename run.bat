@echo off
chcp 65001 >nul
title Seedance AI Video Generator

echo ===================================================
echo     Seedance AI Video Generator
echo ===================================================
echo.

REM Perehod v papku skripta
cd /d "%~dp0"

REM Proverka Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found / Python ne nayden!
    echo Please install Python 3.10+ and add it to PATH.
    pause
    exit /b
)

REM Proverka zavisimostey
echo [1/2] Checking dependencies (gradio, requests)...
python -c "import gradio, requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b
    )
)

REM Zapusk
echo [2/2] Launching Gradio Web UI...
echo.
echo URL: http://127.0.0.1:7860
echo.
python app.py

pause
