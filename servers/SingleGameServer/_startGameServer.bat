@echo off
title Zombie Game - Native GUI

echo ============================================
echo   ZOMBIE GAME - Native Windows GUI
echo ============================================
echo.
echo Pure Windows interface - No web browser!
echo.

python zombie_game_native.py

if errorlevel 1 (
    echo.
    echo ERROR: Application failed to start
    echo.
    echo To install dependencies:
    echo pip install flask
    echo.
)

pause
