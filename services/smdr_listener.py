import socket
import threading
import re
from datetime import datetime
from .smdr_parser import parse_and_save

# Global status shared across threads
status = {
    'connected': False,
    'ip': '',
    'last_seen': None
}

def start_listener(ip, port, db_path):
    global status
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((ip, port))
        sock.listen(5)
        print(f"[LISTENING] TCP port {port}")
        while True:
            client, addr = sock.accept()
            print(f"[CONNECTED] {addr}")
            # Update status: connected
            status['connected'] = True
            status['ip'] = addr[0]
            status['last_seen'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            client.settimeout(3)
            data = b""
            try:
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            except socket.timeout:
                pass
            client.close()

            if data:
                text = data.decode('utf-8', errors='ignore')
                for match in re.finditer(r'(\d{4}/\d{2}/\d{2}\s\d{2}:\d{2}:\d{2},.*)', text):
                    parse_and_save(match.group(0), db_path)
                # Update last seen after successful data
                status['last_seen'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Connection closed
            status['connected'] = False

    except Exception as e:
        print(f"[LISTENER ERROR] {e}")
        status['connected'] = False
        threading.Event().wait(5)