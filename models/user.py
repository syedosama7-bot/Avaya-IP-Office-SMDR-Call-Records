from .database import get_db
from werkzeug.security import generate_password_hash

def get_user_by_username(username):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, password_hash, role, extension,
               email, email_reports_enabled, email_alerts_enabled
        FROM users WHERE username = ?
    """, (username,))
    row = cursor.fetchone()
    conn.close()
    return row

def create_user(username, password, role, extension=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, password_hash, role, extension) VALUES (?, ?, ?, ?)",
                   (username, generate_password_hash(password), role, extension))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, role, extension,
               email, email_reports_enabled, email_alerts_enabled
        FROM users
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_by_id(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, role, extension, password_hash,
               email, email_reports_enabled, email_alerts_enabled
        FROM users WHERE id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_user(user_id, password=None, role=None, extension=None):
    conn = get_db()
    cursor = conn.cursor()
    if password:
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(password), user_id))
    if role:
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    if extension is not None:
        cursor.execute("UPDATE users SET extension = ? WHERE id = ?", (extension, user_id))
    conn.commit()
    conn.close()

def update_last_seen(user_id, ip):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_seen = datetime('now', 'localtime'), last_ip = ? WHERE id = ?", (ip, user_id))
    conn.commit()
    conn.close()

def get_active_users():
    """Return users who have been active in the last 15 minutes."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, role, extension, last_seen, last_ip
        FROM users
        WHERE last_seen > datetime('now', '-15 minutes', 'localtime')
        ORDER BY last_seen DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def force_logout_user(user_id):
    """Marks a user for forced logout on next request."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO force_logout (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def update_user_email(user_id, email):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
    conn.commit()
    conn.close()

def update_user_email_preferences(user_id, reports_enabled=None, alerts_enabled=None):
    conn = get_db()
    cursor = conn.cursor()
    if reports_enabled is not None:
        cursor.execute("UPDATE users SET email_reports_enabled = ? WHERE id = ?", (1 if reports_enabled else 0, user_id))
    if alerts_enabled is not None:
        cursor.execute("UPDATE users SET email_alerts_enabled = ? WHERE id = ?", (1 if alerts_enabled else 0, user_id))
    conn.commit()
    conn.close()