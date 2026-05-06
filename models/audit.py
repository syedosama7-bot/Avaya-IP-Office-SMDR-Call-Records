from .database import get_db
from datetime import datetime
from flask import request

MAX_AUDIT_ROWS = 100000

def log_action(user_id, action):
    conn = get_db()
    cursor = conn.cursor()
    ip = request.remote_addr or 'unknown'
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO audit_log (user_id, action, ip_address, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, action, ip, timestamp)
    )
    conn.commit()
    # Purge old entries if the table exceeds the limit
    cursor.execute("SELECT COUNT(*) FROM audit_log")
    count = cursor.fetchone()[0]
    if count > MAX_AUDIT_ROWS:
        # Delete the oldest entries, keeping only the newest MAX_AUDIT_ROWS
        cursor.execute("DELETE FROM audit_log WHERE id NOT IN (SELECT id FROM audit_log ORDER BY id DESC LIMIT ?)", (MAX_AUDIT_ROWS,))
        conn.commit()
    conn.close()

def get_audit_logs(page=1, per_page=50):
    """Returns (logs, total_count) for the given page."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log")
    total = cursor.fetchone()[0]
    offset = (page - 1) * per_page
    cursor.execute("""
        SELECT a.id, u.username, a.action, a.ip_address, a.timestamp
        FROM audit_log a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    logs = cursor.fetchall()
    conn.close()
    return logs, total

def get_all_audit_logs():
    """Returns all audit logs (for CSV export)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, u.username, a.action, a.ip_address, a.timestamp
        FROM audit_log a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC
        LIMIT 100000
    """)
    logs = cursor.fetchall()
    conn.close()
    return logs