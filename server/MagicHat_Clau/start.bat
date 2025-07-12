
echo Starting server...
netsh advfirewall firewall add rule name="Baza Game Server" dir=in action=allow protocol=TCP localport=5000
python server.py
pause