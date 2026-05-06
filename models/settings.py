from .database import get_db

DEFAULTS = {
    'smdr_ip': '0.0.0.0',
    'smdr_port': '9001',
    'web_host': '0.0.0.0',
    'web_port': '5000',
    'backup_path': '',                # empty means disabled
    'backup_interval_hours': '24',    # daily by default
    'last_backup_time': '',           # timestamp of last automatic backup
    'last_backup_status': ''          # success/failure message
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
    # Fill missing keys with defaults
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
    """data is a dict with key/values to update."""
    for k, v in data.items():
        if k in DEFAULTS:   # only allow known keys
            set_setting(k, v)