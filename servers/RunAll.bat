ECHO Starting BAZA servers

echo DISCOVER SERVER
start "DISCOVER SERVER" /D "%Disco"   disco.bat
start "FILE SERVER" /D "%FileServer"  fs_start.bat
rem start "OTA COPY" /D %OtaServer" xCopy.bat
rem pause
rem start "OTA SERVER"  /D "%OtaServer" ota.bat
start "GAME SERVER" /D "%MagicHat"    start.bat
start http://localhost:5000

pause