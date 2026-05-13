import socket
import threading
import re
import logging
import sqlite3
import json
from datetime import datetime
from .smdr_parser import parse_and_save

DB_PATH = None
logger = logging.getLogger(__name__)

# ---------- Direct DB helpers (no Flask context) ----------
def _get_setting(key):
    """Fetch a setting directly from the database, no Flask context."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ''
    except Exception as e:
        logger.error(f"Direct get_setting error: {e}")
        return ''

def _set_setting(key, value):
    """Write a setting directly, no Flask context."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Direct set_setting error: {e}")

def _update_pabx_status(ip, name, connected=None, last_seen=None):
    """Update the global PABX status JSON stored in settings."""
    status_json = _get_setting('pabx_status')
    try:
        status = json.loads(status_json) if status_json else {}
    except json.JSONDecodeError:
        status = {}
    entry = status.get(ip, {'name': name, 'connected': False})
    entry['name'] = name
    if connected is not None:
        entry['connected'] = connected
    if last_seen:
        entry['last_seen'] = last_seen
    status[ip] = entry
    _set_setting('pabx_status', json.dumps(status))

# ---------- Listener ----------
def start_listener(ip, port, db_path):
    global DB_PATH
    DB_PATH = db_path

    # Read allowed servers directly from DB
    servers_json = _get_setting('pabx_servers')
    try:
        servers = json.loads(servers_json) if servers_json else []
    except json.JSONDecodeError:
        servers = []
    allowed_ips = {s['ip']: s['name'] for s in servers}

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((ip, port))
        sock.listen(5)
        logger.info(f"SMDR listener started on {ip}:{port}")
        while True:
            client, addr = sock.accept()
            remote_ip = addr[0]
            logger.info(f"SMDR connection from {addr}")

            if not allowed_ips:
                logger.warning(f"Rejected {remote_ip} – no PABX servers configured")
                client.close()
                continue
            if remote_ip not in allowed_ips:
                logger.warning(f"Rejected {remote_ip} – IP not in allowed list")
                client.close()
                continue

            name = allowed_ips[remote_ip]
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _update_pabx_status(remote_ip, name, True, now)

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
                # Only update last_seen, leave connected flag as is (monitor decides online status)
                _update_pabx_status(remote_ip, name, None, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            else:
                logger.warning(f"No data from {remote_ip}")
                _update_pabx_status(remote_ip, name, False, now)

    except Exception as e:
        logger.error(f"SMDR listener error: {e}")
        threading.Event().wait(5)