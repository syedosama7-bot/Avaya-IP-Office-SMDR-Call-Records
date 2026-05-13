from .database import get_db
import json

DEFAULTS = {
    'smdr_ip': '0.0.0.0',
    'smdr_port': '9001',
    'web_host': '0.0.0.0',
    'web_port': '5000',
    'backup_path': '',
    'backup_interval_hours': '24',
    'last_backup_time': '',
    'last_backup_status': '',
    'pabx_servers': '[]',
    'pabx_status': '{}',
    'pabx_online_timeout_minutes': '15',
    'pabx_check_interval_minutes': '5',
    'company_name': 'Avaya CDR',
    'company_logo_url': '',
    'smtp_host': '',
    'smtp_port': '587',
    'smtp_use_tls': '1',
    'smtp_username': '',
    'smtp_password': '',
    'smtp_from_email': '',
    'smtp_from_name': 'Avaya CDR',
    'smtp_protocol': 'starttls',
    'smtp_verify_cert': '1'
}

def get_setting(key):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else DEFAULTS.get(key, '')

def get_all_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    settings = dict(rows)
    for k, v in DEFAULTS.items():
        if k not in settings:
            settings[k] = v
    return settings

def set_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def update_settings(data):
    for k, v in data.items():
        if k in DEFAULTS:
            set_setting(k, v)

# ---------- PABX server management ----------
def get_pabx_servers():
    return json.loads(get_setting('pabx_servers'))

def save_pabx_servers(servers):
    set_setting('pabx_servers', json.dumps(servers))

def add_pabx_server(name, ip, monitor_port=80):
    servers = get_pabx_servers()
    if any(s['ip'] == ip for s in servers):
        return False
    servers.append({'name': name, 'ip': ip, 'monitor_port': int(monitor_port)})
    save_pabx_servers(servers)
    return True

def remove_pabx_server(ip):
    servers = [s for s in get_pabx_servers() if s['ip'] != ip]
    save_pabx_servers(servers)

# ---------- PABX status (persistent) ----------
def get_pabx_status():
    return json.loads(get_setting('pabx_status'))

def update_pabx_status(ip, name, connected, last_seen=None):
    status = get_pabx_status()
    entry = status.get(ip, {'name': name})
    entry['name'] = name
    entry['connected'] = connected
    if last_seen:
        entry['last_seen'] = last_seen
    status[ip] = entry
    set_setting('pabx_status', json.dumps(status))