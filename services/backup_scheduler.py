import os
import shutil
import json
import threading
import time
import sqlite3
from datetime import datetime

def get_all_settings_no_context(db_path):
    """Fetch all settings using a direct database path (no Flask context)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    settings = dict(rows)
    # Fill missing defaults
    DEFAULTS = {
        'backup_path': '',
        'backup_interval_hours': '24',
        'last_backup_time': '',
        'last_backup_status': ''
    }
    for k, v in DEFAULTS.items():
        if k not in settings:
            settings[k] = v
    return settings

def set_setting_no_context(db_path, key, value):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def perform_backup(db_path, backup_dir):
    """Copy database and export configuration, then update status."""
    try:
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        db_backup = os.path.join(backup_dir, f'smdr_records_backup_{timestamp}.db')
        shutil.copy2(db_path, db_backup)

        # Export configuration
        settings = get_all_settings_no_context(db_path)
        config_backup = os.path.join(backup_dir, f'avaya_cdr_config_{timestamp}.json')
        with open(config_backup, 'w') as f:
            json.dump(settings, f, indent=2)

        set_setting_no_context(db_path, 'last_backup_time', timestamp)
        set_setting_no_context(db_path, 'last_backup_status', 'Success')
        print(f"[BACKUP] Completed at {timestamp} → {backup_dir}")
    except Exception as e:
        set_setting_no_context(db_path, 'last_backup_time', datetime.now().strftime('%Y%m%d_%H%M%S'))
        set_setting_no_context(db_path, 'last_backup_status', f'Failed: {str(e)}')
        print(f"[BACKUP ERROR] {e}")

def start_backup_scheduler(db_path):
    """Starts a background thread that performs backups based on settings."""
    def run():
        while True:
            try:
                settings = get_all_settings_no_context(db_path)
                interval_hours = int(settings.get('backup_interval_hours', '0'))
                backup_path = settings.get('backup_path', '').strip()

                if backup_path and interval_hours > 0:
                    perform_backup(db_path, backup_path)
                else:
                    # If disabled, sleep for 1 hour and re-check
                    interval_hours = 1

                time.sleep(interval_hours * 3600)
            except Exception as e:
                print(f"[BACKUP SCHEDULER ERROR] {e}")
                time.sleep(300)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print("[BACKUP] Scheduler started")