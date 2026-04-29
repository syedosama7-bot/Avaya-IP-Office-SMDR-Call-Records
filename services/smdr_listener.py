import socket
import threading
import re
from .smdr_parser import parse_and_save

DB_PATH = None  # will be set from app factory

def start_listener(ip, port, db_path):
    global DB_PATH
    DB_PATH = db_path
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((ip, port))
        sock.listen(5)
        print(f"[LISTENING] TCP port {port}")
        while True:
            client, addr = sock.accept()
            print(f"[CONNECTED] {addr}")
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
                    parse_and_save(match.group(0), DB_PATH)
    except Exception as e:
        print(f"[LISTENER ERROR] {e}")
        threading.Event().wait(5)