rem netsh advfirewall firewall add rule name="Baza Disco Server" dir=in action=allow protocol=UDP localport=4210
rem pip install psutil
python disco_gui.py
pause