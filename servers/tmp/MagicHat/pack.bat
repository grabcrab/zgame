@echo off
echo Checking installed Python packages...
echo.

:: Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Python is not installed or not found in PATH.
    pause
    exit /b 1
)

:: Check installed packages
echo List of installed Python packages:
python -m pip list
if %ERRORLEVEL% neq 0 (
    echo Failed to retrieve package list.
    pause
    exit /b 1
)

echo.
echo Check complete.
pause