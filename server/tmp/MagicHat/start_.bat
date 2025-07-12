@echo off
echo Setting up server environment...
echo.

:: Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Python is not installed or not found in PATH.
    pause
    exit /b 1
)

:: Check if Flask is installed
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Flask is not installed. Installing Flask...
    python -m pip install flask
    if %ERRORLEVEL% neq 0 (
        echo Failed to install Flask.
        pause
        exit /b 1
    )
)

:: Check if server.py exists
if not exist server.py (
    echo server.py not found in the current directory.
    pause
    exit /b 1
)

:: Configure Windows Firewall to allow port 5000
echo Configuring Windows Firewall...
netsh advfirewall firewall add rule name="Allow Flask Server Port 5000" dir=in action=allow protocol=TCP localport=5000 >nul
if %ERRORLEVEL% neq 0 (
    echo Failed to configure firewall. Trying with elevated privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall add rule name=\"Allow Flask Server Port 5000\" dir=in action=allow protocol=TCP localport=5000' -Verb RunAs"
    if %ERRORLEVEL% neq 0 (
        echo Failed to configure firewall. Please check permissions or manually allow port 5000.
        pause
        exit /b 1
    )
)

:: Start the server
echo Starting server...
python server.py
if %ERRORLEVEL% neq 0 (
    echo Failed to start server.
    pause
    exit /b 1
)

pause