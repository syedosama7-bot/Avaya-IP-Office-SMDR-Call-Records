import sqlite3
from flask import current_app
from werkzeug.security import generate_password_hash

def get_db():
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(current_app.config['DATABASE'])
    cursor = conn.cursor()

    # Calls table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_start TEXT,
            duration_raw TEXT,
            duration_seconds INTEGER,
            ring_time INTEGER DEFAULT 0,
            caller TEXT,
            direction TEXT,
            called_num TEXT,
            dialled_num TEXT,
            account_code TEXT,
            is_internal INTEGER,
            call_id INTEGER,
            continuation INTEGER,
            party1_device TEXT,
            party1_name TEXT,
            party2_device TEXT,
            party2_name TEXT,
            hold_time INTEGER DEFAULT 0,
            park_time INTEGER DEFAULT 0,
            auth_valid INTEGER,
            auth_code TEXT,
            cost REAL DEFAULT 0.0,
            external_targeting_cause TEXT,
            external_targeter_id TEXT,
            external_targeted_number TEXT
        )
    ''')

    cursor.execute("PRAGMA table_info(calls)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    desired_columns = {
        'ring_time': 'INTEGER DEFAULT 0',
        'dialled_num': 'TEXT',
        'account_code': 'TEXT',
        'call_id': 'INTEGER',
        'continuation': 'INTEGER',
        'party1_device': 'TEXT',
        'party1_name': 'TEXT',
        'party2_device': 'TEXT',
        'party2_name': 'TEXT',
        'hold_time': 'INTEGER DEFAULT 0',
        'park_time': 'INTEGER DEFAULT 0',
        'auth_valid': 'INTEGER',
        'auth_code': 'TEXT',
        'external_targeting_cause': 'TEXT',
        'external_targeter_id': 'TEXT',
        'external_targeted_number': 'TEXT',
    }
    for col_name, col_type in desired_columns.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE calls ADD COLUMN {col_name} {col_type}")
                print(f"[MIGRATION] Added column '{col_name}'")
            except sqlite3.OperationalError as e:
                print(f"[WARN] Could not add column {col_name}: {e}")

    # Tariffs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefix TEXT UNIQUE,
            description TEXT,
            rate_per_minute REAL
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO tariffs (prefix, description, rate_per_minute) VALUES ('local', 'Default Rate', 1.0)")

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            extension TEXT
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                   ('admin', generate_password_hash('admin123'), 'admin'))

    # Migrate missing user columns
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [row[1] for row in cursor.fetchall()]
    user_new = {
        'last_seen': 'TEXT',
        'last_ip': 'TEXT',
        'email': 'TEXT',
        'email_reports_enabled': 'INTEGER DEFAULT 1',
        'email_alerts_enabled': 'INTEGER DEFAULT 1',
    }
    for col, col_type in user_new.items():
        if col not in user_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                print(f"[MIGRATION] Added column '{col}' to users")
            except sqlite3.OperationalError:
                pass

    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Audit log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            ip_address TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Force logout table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS force_logout (
            user_id INTEGER PRIMARY KEY
        )
    ''')

    # Email log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            to_email TEXT,
            subject TEXT,
            status TEXT,
            error_message TEXT,
            sent_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Report subscriptions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS report_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_type TEXT NOT NULL,
            frequency TEXT NOT NULL,
            schedule_day INTEGER DEFAULT 0,
            schedule_time TEXT DEFAULT '08:00',
            enabled INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ... at the end of init_db, after the existing report_subscriptions CREATE TABLE:

    # Migrate filter_params column for report_subscriptions
    cursor.execute("PRAGMA table_info(report_subscriptions)")
    sub_columns = [row[1] for row in cursor.fetchall()]
    if 'filter_params' not in sub_columns:
        try:
            cursor.execute("ALTER TABLE report_subscriptions ADD COLUMN filter_params TEXT")
            print("[MIGRATION] Added column 'filter_params' to report_subscriptions")
        except sqlite3.OperationalError as e:
            print(f"[WARN] Could not add column filter_params: {e}")


    # Alert subscriptions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()
    print("[OK] Database Ready (with users)")