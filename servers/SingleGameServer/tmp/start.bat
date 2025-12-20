@echo off
REM Simple Zombie Game Launcher
title Zombie Game

echo Starting Zombie Game...
echo.

python zombie_game_app.py

if errorlevel 1 (
    echo.
    echo ERROR: Application failed to start
    echo.
    echo Common issues:
    echo - Python not installed or not in PATH
    echo - Missing dependencies: run "pip install -r requirements.txt"
    echo - Missing templates: run "python setup.py"
    echo.
)

pause
