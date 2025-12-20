@echo off
REM ============================================================
REM xGAME Discovery Server - Firewall Setup Script
REM Run this script as Administrator
REM ============================================================

echo.
echo ================================================
echo xGAME Discovery Server - Firewall Setup
echo ================================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click on this file and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo Running as Administrator... OK
echo.

REM Remove old rules if they exist
echo Cleaning up old firewall rules...
netsh advfirewall firewall delete rule name="Baza Disco Server" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME Disco Server - UDP IN" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME Disco Server - UDP OUT" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME Disco Server - Broadcast" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME TCP Server - IN" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME TCP Server - OUT" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME Disco Server - Python" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME Disco Server - Python OUT" >nul 2>&1
echo Done.
echo.

REM Add UDP inbound rule for discovery port
echo [1/6] Adding UDP inbound rule (port 4210)...
netsh advfirewall firewall add rule name="xGAME Disco Server - UDP IN" dir=in action=allow protocol=UDP localport=4210
if %errorLevel% neq 0 (
    echo ERROR: Failed to add inbound rule
    pause
    exit /b 1
)
echo OK
echo.

REM Add UDP outbound rule for discovery port
echo [2/6] Adding UDP outbound rule (port 4210)...
netsh advfirewall firewall add rule name="xGAME Disco Server - UDP OUT" dir=out action=allow protocol=UDP localport=4210
if %errorLevel% neq 0 (
    echo ERROR: Failed to add outbound rule
    pause
    exit /b 1
)
echo OK
echo.

REM Add broadcast rule
echo [3/6] Adding broadcast rule...
netsh advfirewall firewall add rule name="xGAME Disco Server - Broadcast" dir=in action=allow protocol=UDP localport=4210 remoteip=any
if %errorLevel% neq 0 (
    echo WARNING: Failed to add broadcast rule (not critical)
) else (
    echo OK
)
echo.

REM Add TCP rules (optional, for main server)
echo [4/6] Adding TCP inbound rule (port 3232)...
netsh advfirewall firewall add rule name="xGAME TCP Server - IN" dir=in action=allow protocol=TCP localport=3232
if %errorLevel% neq 0 (
    echo WARNING: Failed to add TCP inbound rule
) else (
    echo OK
)
echo.

echo [5/6] Adding TCP outbound rule (port 3232)...
netsh advfirewall firewall add rule name="xGAME TCP Server - OUT" dir=out action=allow protocol=TCP localport=3232
if %errorLevel% neq 0 (
    echo WARNING: Failed to add TCP outbound rule
) else (
    echo OK
)
echo.

REM Detect Python path and add rules
echo [6/6] Detecting Python installation...
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    set PYTHON_PATH=%%i
    goto :found_python
)

echo WARNING: Python not found in PATH
echo You may need to manually add Python to firewall rules
goto :skip_python

:found_python
echo Found Python at: %PYTHON_PATH%
echo Adding Python executable to firewall...
netsh advfirewall firewall add rule name="xGAME Disco Server - Python" dir=in action=allow program="%PYTHON_PATH%" enable=yes
netsh advfirewall firewall add rule name="xGAME Disco Server - Python OUT" dir=out action=allow program="%PYTHON_PATH%" enable=yes
echo OK
echo.

:skip_python

echo.
echo ================================================
echo Firewall Configuration Complete!
echo ================================================
echo.
echo The following rules have been added:
echo   - UDP port 4210 (IN/OUT) for discovery
echo   - TCP port 3232 (IN/OUT) for main server
echo   - Broadcast traffic allowed
echo   - Python executable allowed (if found)
echo.
echo Your xGAME Discovery Server should now work properly!
echo.
echo To view the rules in Windows Firewall:
echo   1. Open Windows Defender Firewall
echo   2. Click "Advanced settings"
echo   3. Look for rules starting with "xGAME"
echo.
pause
