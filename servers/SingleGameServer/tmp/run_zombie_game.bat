@echo off
REM Zombie Game - Windows Launcher
title Zombie Game Launcher

echo ============================================
echo Zombie Game - Starting Application
echo ============================================
echo.

REM Check if Python is installed
python --version 2>nul
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Check if dependencies are installed
echo Checking dependencies...
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Flask not found. Installing dependencies...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies
        echo Please run: pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo.
    echo Dependencies installed successfully!
    echo.
)

REM Check if templates exist
if not exist "templates\main.html" (
    echo Templates not found. Running setup...
    echo.
    python setup.py
    if errorlevel 1 (
        echo.
        echo ERROR: Setup failed
        echo Please ensure template files are available
        echo.
        pause
        exit /b 1
    )
    echo.
)

REM Run the application
echo.
echo Starting Zombie Game...
echo.
echo ============================================
echo.
echo If the application window doesn't appear,
echo check the messages below for errors.
echo.
echo To close: Close the application window or press Ctrl+C here
echo.
echo ============================================
echo.

python zombie_game_app.py

REM Check if there was an error
if errorlevel 1 (
    echo.
    echo ============================================
    echo ERROR: Application exited with an error
    echo ============================================
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Application closed successfully
echo ============================================
echo.
pause
