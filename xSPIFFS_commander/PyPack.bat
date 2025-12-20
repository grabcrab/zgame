@echo off
REM ==============================================================
REM ESP32 SPIFFS Manager – Automated Setup & Requirements Installer
REM ==============================================================

echo.
echo ==============================================================
echo ESP32 SPIFFS Manager  –  Setup & Requirements Installer
echo ==============================================================
echo.

:: --------------------------------------------------------------
::  1️⃣  Verify that a usable Python interpreter is on the PATH
:: --------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in your PATH!
    echo Please download and install Python from:
    echo   https://www.python.org/downloads/
    echo Make sure to tick “Add Python to PATH” during installation.
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

:: --------------------------------------------------------------
::  2️⃣  Verify that pip (the Python package manager) is available
:: --------------------------------------------------------------
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available!
    echo Re‑install Python and be sure the “pip” component is selected.
    echo.
    pause
    exit /b 1
)

echo pip found:
pip --version
echo.

:: --------------------------------------------------------------
::  3️⃣  Install / upgrade the required third‑party packages
:: --------------------------------------------------------------
echo Installing required Python packages (latest versions)...
echo ==============================================================
echo.

:: ---- pyserial ------------------------------------------------
echo Installing/Updating pyserial...
pip install -U pyserial
if errorlevel 1 (
    echo ERROR: Failed to install/upgrade pyserial!
    echo.
    pause
    exit /b 1
)
echo pyserial installed/updated successfully.
echo.

:: ---- esptool -------------------------------------------------
echo Installing/Updating esptool (required for ESP32 communication)...
pip install -U esptool
if errorlevel 1 (
    echo ERROR: Failed to install/upgrade esptool!
    echo.
    pause
    exit /b 1
)
echo esptool installed/updated successfully.
echo.

:: --------------------------------------------------------------
::  4️⃣  Verify that the standard library modules we rely on exist
:: --------------------------------------------------------------
echo ==============================================================
echo Testing that all required modules are importable...
echo ==============================================================
python - <<END
import sys

# Modules that must be importable (standard‑library or installed above)
required = [
    'tkinter',          # GUI – ships with the CPython distribution
    'serial',           # pyserial (installed above)
    'esptool',          # installed above
    'json',
    'subprocess',
    'pathlib',
    'threading',
    'os',
]

missing = []

for mod in required:
    try:
        __import__(mod)
        print(f'✓ {mod}')
    except ImportError as e:
        print(f'✗ {mod} – {e}')
        missing.append(mod)

if missing:
    print(f'\nERROR: The following required modules could not be imported: {missing}')
    sys.exit(1)
else:
    print('\nAll required modules are available!')
    sys.exit(0)
END

if errorlevel 1 (
    echo.
    echo ==============================================================
    echo ERROR: One or more required modules are missing.
    echo Please review the messages above and resolve the issues.
    echo ==============================================================
    pause
    exit /b 1
)

:: --------------------------------------------------------------
::  5️⃣  Verify that tkinter can actually create a window
:: --------------------------------------------------------------
echo Checking tkinter runtime availability...
python -c "import tkinter; tkinter.Tk().withdraw()" 2>nul
if errorlevel 1 (
    echo WARNING: tkinter could not be initialized!
    echo On Windows it normally ships with Python, but on some Linux
    echo distributions you may need to install it manually, e.g.:
    echo   sudo apt-get install python3-tk
    echo.
)

:: --------------------------------------------------------------
::  6️⃣  Final success message & next steps
:: --------------------------------------------------------------
echo.
echo ==============================================================
echo Setup completed successfully!
echo ==============================================================
echo.
echo You can now start the ESP32 SPIFFS Manager with one of the following:
echo   1. Double‑click the script file  (spiffs_commander.py)
echo   2. From a command prompt:
echo        python spiffs_commander.py
echo.
echo Make sure the following files are present in the same folder:
echo   - esptool.exe
echo   - mkspiffs_espressif32_arduino.exe
echo   - spiffs_commander.py
echo.
echo Press any key to exit…
pause >nul
