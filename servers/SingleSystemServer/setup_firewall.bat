@echo off
:: ============================================================
:: xGAME Server Manager - Firewall Rules Setup
:: Run this script as Administrator
:: ============================================================

echo.
echo ============================================================
echo xGAME Server Manager - Firewall Rules Setup
echo ============================================================
echo.

:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires Administrator privileges!
    echo Please right-click and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo Creating firewall rules...
echo.

:: ============================================================
:: Discovery Server (UDP)
:: ============================================================
echo [1/6] Removing old Discovery Server rules (if exist)...
netsh advfirewall firewall delete rule name="xGAME Discovery Server (UDP In)" >nul 2>&1
netsh advfirewall firewall delete rule name="xGAME Discovery Server (UDP Out)" >nul 2>&1

echo [2/6] Adding Discovery Server UDP Inbound rule (port 4210)...
netsh advfirewall firewall add rule ^
    name="xGAME Discovery Server (UDP In)" ^
    dir=in ^
    action=allow ^
    protocol=UDP ^
    localport=4210 ^
    profile=any ^
    enable=yes ^
    description="Allow ESP32 discovery requests on UDP port 4210"

echo [3/6] Adding Discovery Server UDP Outbound rule (port 4210)...
netsh advfirewall firewall add rule ^
    name="xGAME Discovery Server (UDP Out)" ^
    dir=out ^
    action=allow ^
    protocol=UDP ^
    localport=4210 ^
    profile=any ^
    enable=yes ^
    description="Allow ESP32 discovery responses on UDP port 4210"

:: ============================================================
:: File Server (TCP)
:: ============================================================
echo [4/6] Removing old File Server rule (if exists)...
netsh advfirewall firewall delete rule name="xGAME File Server (TCP)" >nul 2>&1

echo [5/6] Adding File Server TCP rule (port 5001)...
netsh advfirewall firewall add rule ^
    name="xGAME File Server (TCP)" ^
    dir=in ^
    action=allow ^
    protocol=TCP ^
    localport=5001 ^
    profile=any ^
    enable=yes ^
    description="Allow ESP32 file sync connections on TCP port 5001"

:: ============================================================
:: OTA Server (TCP)
:: ============================================================
echo [6/6] Removing old OTA Server rule (if exists)...
netsh advfirewall firewall delete rule name="xGAME OTA Server (TCP)" >nul 2>&1

echo [6/6] Adding OTA Server TCP rule (port 5005)...
netsh advfirewall firewall add rule ^
    name="xGAME OTA Server (TCP)" ^
    dir=in ^
    action=allow ^
    protocol=TCP ^
    localport=5005 ^
    profile=any ^
    enable=yes ^
    description="Allow ESP32 OTA update connections on TCP port 5005"

echo.
echo ============================================================
echo Firewall rules created successfully!
echo ============================================================
echo.
echo Rules added:
echo   - xGAME Discovery Server (UDP In)  - Port 4210
echo   - xGAME Discovery Server (UDP Out) - Port 4210
echo   - xGAME File Server (TCP)          - Port 5001
echo   - xGAME OTA Server (TCP)           - Port 5005
echo.
echo If you change ports in Settings, run this script again
echo with the updated port numbers.
echo.
pause
