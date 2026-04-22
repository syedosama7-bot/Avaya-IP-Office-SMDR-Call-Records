from flask import Flask, render_template, request
import sqlite3
import socket
import threading
import csv
import re
import os
from io import StringIO
from datetime import timedelta

app = Flask(__name__)

# -------------------------------------------------------------------
# ABSOLUTE PATH TO DATABASE – CHANGE THIS IF NEEDED
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'smdr_records.db')
# Or hardcode if you prefer:
# DB_PATH = r"I:\Gen AI Pak angels\IPOFFICE SMDR Project osama\smdr_records.db"

LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 9001

# -------------------------------------------------------------------
# DATABASE INITIALISATION – UPDATED SCHEMA WITH MORE SMDR FIELDS
# -------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create table with all required columns if not exists
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

    # If table already existed, add any missing columns (migration)
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

    # Tariffs table (unchanged)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefix TEXT UNIQUE,
            description TEXT,
            rate_per_minute REAL
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO tariffs (prefix, description, rate_per_minute) VALUES ('local', 'Default Rate', 1.0)")
    conn.commit()
    conn.close()
    print("[OK] Database Ready")

# -------------------------------------------------------------------
# PARSE SMDR RAW DATA AND SAVE TO DATABASE (EXPANDED FIELDS)
# -------------------------------------------------------------------
def parse_and_save(raw_data):
    match = re.search(r'(\d{4}/\d{2}/\d{2}\s\d{2}:\d{2}:\d{2},.*)', raw_data)
    if not match:
        return

    try:
        line = match.group(1).strip()
        row = next(csv.reader(StringIO(line)))

        # Ensure we have at least 30 fields (pad with empty strings)
        while len(row) < 30:
            row.append('')

        # Extract fields with safe parsing
        call_start   = row[0]
        duration     = row[1]
        ring_time    = int(row[2]) if row[2].strip().isdigit() else 0
        caller       = row[3]
        direction    = "Inbound" if row[4] == "I" else "Outbound"
        called_num   = row[5]
        dialled_num  = row[6]
        account_code = row[7]
        is_int_raw   = int(row[8]) if row[8].strip().isdigit() else 0
        call_id      = int(row[9]) if row[9].strip().isdigit() else None
        continuation = int(row[10]) if row[10].strip().isdigit() else 0
        party1_dev   = row[11]
        party1_name  = row[12]
        party2_dev   = row[13]
        party2_name  = row[14]
        hold_time    = int(row[15]) if row[15].strip().isdigit() else 0
        park_time    = int(row[16]) if row[16].strip().isdigit() else 0
        auth_valid   = int(row[17]) if row[17].strip().isdigit() else 0
        auth_code    = row[18] if row[18] != 'n/a' else None

        # Calculate duration in seconds
        h, m, s = map(int, duration.split(':'))
        sec = (h * 3600) + (m * 60) + s

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO calls 
                (call_start, duration_raw, duration_seconds, ring_time,
                 caller, direction, called_num, dialled_num, account_code,
                 is_internal, call_id, continuation, party1_device, party1_name,
                 party2_device, party2_name, hold_time, park_time,
                 auth_valid, auth_code, cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (call_start, duration, sec, ring_time,
                  caller, direction, called_num, dialled_num, account_code,
                  is_int_raw, call_id, continuation, party1_dev, party1_name,
                  party2_dev, party2_name, hold_time, park_time,
                  auth_valid, auth_code, 0.0))
        print(f"[SAVED] {party1_name} | {caller} -> {called_num}")

    except Exception as e:
        print(f"[!] Parse Error: {e}")

# -------------------------------------------------------------------
# TCP LISTENER – RECEIVES SMDR STREAM FROM AVAYA
# -------------------------------------------------------------------
def tcp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((LISTEN_IP, LISTEN_PORT))
        sock.listen(5)
        print(f"[LISTENING] TCP port {LISTEN_PORT}")
        while True:
            client, addr = sock.accept()
            print(f"[CONNECTED] {addr}")
            data = client.recv(4096).decode('utf-8', errors='ignore')
            if data:
                parse_and_save(data)
            client.close()
    except Exception as e:
        print(f"[LISTENER ERROR] {e}")
        threading.Event().wait(5)

# -------------------------------------------------------------------
# MAIN DASHBOARD ROUTE WITH FILTERS AND SUMMARY
# -------------------------------------------------------------------
@app.route('/')
def index():
    # Get filter parameters
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    direction = request.args.get('direction', '')
    is_internal = request.args.get('is_internal', '')
    search = request.args.get('search', '')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Build WHERE clause dynamically
    conditions = []
    params = []

    if start_date:
        conditions.append("call_start >= ?")
        params.append(start_date + " 00:00:00")
    if end_date:
        conditions.append("call_start <= ?")
        params.append(end_date + " 23:59:59")
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if is_internal:
        if is_internal == 'internal':
            conditions.append("is_internal = 1")
        elif is_internal == 'external':
            conditions.append("is_internal = 0")
    if search:
        conditions.append("(caller LIKE ? OR called_num LIKE ? OR party1_name LIKE ? OR party2_name LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like, like])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Get filtered calls (including new fields)
    query = f"""
        SELECT id, call_start, duration_raw, ring_time, caller, direction,
               called_num, is_internal, party1_name, party2_name, hold_time, cost
        FROM calls
        {where_clause}
        ORDER BY id DESC
        LIMIT 100
    """
    cursor.execute(query, params)
    calls = cursor.fetchall()

    # Summary statistics
    summary_query = f"""
        SELECT
            COUNT(*) as total_calls,
            SUM(duration_seconds) as total_seconds,
            AVG(duration_seconds) as avg_seconds,
            SUM(ring_time) as total_ring,
            SUM(hold_time) as total_hold,
            SUM(cost) as total_cost
        FROM calls
        {where_clause}
    """
    cursor.execute(summary_query, params)
    stats = cursor.fetchone()
    conn.close()

    # Format summary values
    total_calls = stats[0] or 0
    total_duration = str(timedelta(seconds=stats[1] if stats[1] else 0))
    avg_duration = str(timedelta(seconds=int(stats[2] if stats[2] else 0)))
    total_ring = str(timedelta(seconds=stats[3] if stats[3] else 0))
    total_hold = str(timedelta(seconds=stats[4] if stats[4] else 0))
    total_cost = round(stats[5] or 0, 2)

    summary = {
        'total_calls': total_calls,
        'total_duration': total_duration,
        'avg_duration': avg_duration,
        'total_ring': total_ring,
        'total_hold': total_hold,
        'total_cost': total_cost
    }

    return render_template('index.html',
                           records=calls,
                           summary=summary,
                           filters={
                               'start_date': start_date,
                               'end_date': end_date,
                               'direction': direction,
                               'is_internal': is_internal,
                               'search': search
                           })

# -------------------------------------------------------------------
# DEBUG ROUTE – CHECK DATABASE CONTENT
# -------------------------------------------------------------------
@app.route('/raw')
def raw_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM calls")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT * FROM calls ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    output = f"Path: {DB_PATH}\nTotal records: {count}\n\n"
    for row in rows:
        output += f"{row}\n"
    return f"<pre>{output}</pre>"

# -------------------------------------------------------------------
# START APPLICATION
# -------------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    threading.Thread(target=tcp_listener, daemon=True).start()
    print("[WEB] Running on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)