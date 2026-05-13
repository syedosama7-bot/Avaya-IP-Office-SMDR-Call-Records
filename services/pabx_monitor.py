import socket
import json
import threading
import time
import logging
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = None

def _get_setting(key):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ''
    except Exception as e:
        logger.error(f"pabx_monitor get_setting error: {e}")
        return ''

def _set_setting(key, value):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"pabx_monitor set_setting error: {e}")

def start_monitor(db_path):
    global DB_PATH
    DB_PATH = db_path

    def run():
        logger.info("PABX monitor thread started")
        while True:
            try:
                servers_json = _get_setting('pabx_servers')
                try:
                    servers = json.loads(servers_json) if servers_json else []
                except json.JSONDecodeError:
                    servers = []

                interval_minutes = int(_get_setting('pabx_check_interval_minutes') or 5)

                for s in servers:
                    ip = s['ip']
                    name = s['name']
                    # Each server can have its own monitor port – default 80 (HTTP)
                    monitor_port = int(s.get('monitor_port', 80))
                    online = False
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(2)
                        sock.connect((ip, monitor_port))
                        sock.close()
                        online = True
                        logger.info(f"PABX ping successful: {name} ({ip}:{monitor_port})")
                    except Exception as e:
                        logger.warning(f"PABX ping failed: {name} ({ip}:{monitor_port}) – {e}")

                    # Update status
                    status_json = _get_setting('pabx_status')
                    try:
                        status = json.loads(status_json) if status_json else {}
                    except json.JSONDecodeError:
                        status = {}
                    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
                    entry = status.get(ip, {'name': name, 'connected': False})
                    entry['name'] = name
                    entry['connected'] = online
                    if online:
                        entry['last_seen'] = now_str
                    status[ip] = entry
                    _set_setting('pabx_status', json.dumps(status))

                time.sleep(interval_minutes * 60)
            except Exception as e:
                logger.error(f"PABX monitor error: {e}")
                time.sleep(30)

    threading.Thread(target=run, daemon=True).start()
    logger.info("PABX monitor started")