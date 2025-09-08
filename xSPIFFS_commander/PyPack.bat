@echo off
REM ESP32 SPIFFS Manager - Install Requirements
REM This batch file installs all required Python packages

echo ====================================
echo ESP32 SPIFFS Manager Setup
echo ====================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available!
    echo Please reinstall Python with pip included.
    echo.
    pause
    exit /b 1
)

echo pip found:
pip --version
echo.

echo Installing required packages...
echo ====================================

REM Install pyserial
echo Installing pyserial...
pip install pyserial
if errorlevel 1 (
    echo ERROR: Failed to install pyserial!
    echo.
    pause
    exit /b 1
)
echo pyserial installed successfully.
echo.

REM Install tkinter (usually comes with Python, but just in case)
echo Checking tkinter availability...
python -c "import tkinter; print('tkinter is available')" 2>nul
if errorlevel 1 (
    echo WARNING: tkinter not found!
    echo tkinter usually comes with Python. You may need to:
    echo - Reinstall Python with tkinter included
    echo - On Linux: sudo apt-get install python3-tk
    echo - On some distributions, install python-tkinter package
    echo.
)

REM Test all required modules
echo ====================================
echo Testing all required modules...
echo ====================================

python -c "
import sys
modules = ['tkinter', 'serial', 'json', 'subprocess', 'pathlib', 'threading', 'os']
failed = []

for module in modules:
    try:
        __import__(module)
        print(f'✓ {module}')
    except ImportError as e:
        print(f'✗ {module} - {e}')
        failed.append(module)

if failed:
    print(f'\nFailed to import: {failed}')
    sys.exit(1)
else:
    print('\nAll required modules are available!')
    sys.exit(0)
"

if errorlevel 1 (
    echo.
    echo ERROR: Some required modules are missing!
    echo Please check the error messages above.
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================
echo Setup completed successfully!
echo ====================================
echo.
echo You can now run the ESP32 SPIFFS Manager by:
echo 1. Double-clicking on spiffs_manager.py
echo 2. Or running: python spiffs_manager.py
echo.
echo Make sure you have the following files in the same directory:
echo - esptool.exe
echo - mkspiffs_espressif32_arduino.exe
echo - spiffs_manager.py
echo.
echo Press any key to exit...
pause >nul