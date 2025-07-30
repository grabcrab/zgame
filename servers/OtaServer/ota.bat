
echo Starting server...
netsh advfirewall firewall add rule name="Baza OTA Server" dir=in action=allow protocol=TCP localport=5005
python ota.py
pause