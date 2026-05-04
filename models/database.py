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
            cost REAL DEFAULT 0.0
        )
    ''')

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

    # Migrate missing columns
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

    # Settings table (for configurable ports)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("[OK] Database Ready (with users)")