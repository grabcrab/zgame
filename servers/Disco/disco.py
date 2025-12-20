import socket, json, psutil, threading, time

DISCO_PORT = 4210
TCP_PORT   = 3232          # whatever your real server uses

def get_preferred_ip():
    for nic, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET:
                ip = a.address
                # skip loopback
                if ip.startswith("127."):  
                    continue
                # skip link-local APIPA
                if ip.startswith("169.254."):
                    continue
                # prefer private LAN ranges
                if (ip.startswith("192.168.") or
                    ip.startswith("10.") or
                    ip.startswith("172.")):
                    return ip
    return '0.0.0.0'

def responder():
    ip = get_preferred_ip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('', DISCO_PORT))
    print(f'Responder listening on :{DISCO_PORT}, will reply with {ip}:{TCP_PORT}')

    while True:
        data, addr = sock.recvfrom(64)
        print(f'Received from {addr}: {data}')  # DEBUG
        if b'ESP32-LOOK' in data:
            response = ip.encode()
            sock.sendto(response, addr)
            print(f'Sent response: {response} to {addr}')  # DEBUG

threading.Thread(target=responder, daemon=True).start()

# keep script alive
while True:
    time.sleep(1)