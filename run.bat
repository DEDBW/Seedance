@echo off
chcp 65001 >nul
title Seedance AI Video Generator

echo ===================================================
echo     🎬 Запуск Seedance AI Video Generator
echo ===================================================
echo.

:: Переходим в директорию скрипта
cd /d "%~dp0"

:: Проверка наличия Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в системе!
    echo Установите Python 3.10+ и добавьте его в PATH.
    pause
    exit /b
)

:: Проверка и установка зависимостей
echo [1/2] Проверка зависимостей (gradio, requests)...
python -c "import gradio, requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo Установка необходимых библиотек...
    python -m pip install gradio requests
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости.
        pause
        exit /b
    )
)

:: Запуск приложения
echo [2/2] Запуск интерфейса Gradio...
echo.
echo Веб-интерфейс будет доступен по адресу: http://127.0.0.1:7860
echo.
python app.py

pause
