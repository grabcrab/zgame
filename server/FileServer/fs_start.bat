
echo Starting server...
netsh advfirewall firewall add rule name="Baza File Server" dir=in action=allow protocol=TCP localport=5001
python file_server.py
pause