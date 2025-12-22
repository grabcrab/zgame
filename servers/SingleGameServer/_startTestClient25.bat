@echo off
title Zombie Game Test

python zombie_test_client.py -n 25

if errorlevel 1 (
    echo.
    echo ERROR: Application failed to start
    echo.
    echo To install dependencies:
    echo pip install flask
    echo.
)

pause
