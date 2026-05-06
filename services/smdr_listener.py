import socket
import threading
import re
import logging
from datetime import datetime
from .smdr_parser import parse_and_save

status = {
    'connected': False,
    'ip': '',
    'last_seen': None
}

DB_PATH = None

logger = logging.getLogger(__name__)

def start_listener(ip, port, db_path):
    global DB_PATH
    DB_PATH = db_path
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((ip, port))
        sock.listen(5)
        logger.info(f"SMDR listener started on {ip}:{port}")
        while True:
            client, addr = sock.accept()
            logger.info(f"SMDR connection from {addr}")
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
                    parse_and_save(match.group(0), DB_PATH)
                status['last_seen'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            else:
                logger.warning("No SMDR data received.")
            status['connected'] = False
    except Exception as e:
        logger.error(f"SMDR listener error: {e}")
        threading.Event().wait(5)