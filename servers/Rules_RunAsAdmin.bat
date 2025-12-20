netsh advfirewall firewall add rule name="Baza Disco Server" dir=in action=allow protocol=UDP localport=4210
netsh advfirewall firewall add rule name="Baza File Server" dir=in action=allow protocol=TCP localport=5001
netsh advfirewall firewall add rule name="Baza Game Server" dir=in action=allow protocol=TCP localport=5000
pause