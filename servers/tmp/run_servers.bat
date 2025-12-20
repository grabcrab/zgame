@echo off
echo Starting BAZA servers

python ScanAllPyPack.py

if not exist "FileServer\" (
    echo ERROR: Folder "FileServer" not found!
    pause
    exit /b 1
)
if not exist "FileServer\file_server.py" (
    echo ERROR: File "file_server.py" not found in FileServer!
    pause
    exit /b 1
)

if not exist "OtaServer\" (
    echo ERROR: Folder "OtaServer" not found!
    pause
    exit /b 1
)
if not exist "OtaServer\ota.py" (
    echo ERROR: File "ota.py" not found in OtaServer!
    pause
    exit /b 1
)

if not exist "MagicHat\" (
    echo ERROR: Folder "MagicHat" not found!
    pause
    exit /b 1
)
if not exist "MagicHat\server.py" (
    echo ERROR: File "server.py" not found in MagicHat!
    pause
    exit /b 1
)

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found! Make sure Python is installed and added to PATH.
    pause
    exit /b 1
)

echo All checks passed. Starting servers...
echo.

echo Starting FILE SERVER...
start "FILE SERVER" /D "%FileServer" python file_server.py
if %errorlevel% neq 0 (
    echo WARNING: Failed to start FILE SERVER
) else (
    echo FILE SERVER started successfully
)

echo Starting OTA SERVER...
start "OTA SERVER" /D "OtaServer" python server.py
if %errorlevel% neq 0 (
    echo WARNING: Failed to start OTA SERVER
) else (
    echo OTA SERVER started successfully
)

echo Starting GAME SERVER...
start "GAME SERVER" /D "%MagicHat" python ota.py
if %errorlevel% neq 0 (
    echo WARNING: Failed to start GAME SERVER
) else (
    echo GAME SERVER started successfully
)

echo.
echo All BAZA servers processing completed!
echo Press any key to exit...
pause >nul