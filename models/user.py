from .database import get_db
from werkzeug.security import generate_password_hash

def get_user_by_username(username):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash, role, extension FROM users WHERE username = ?", (username,))
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
    cursor.execute("SELECT id, username, role, extension FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_by_id(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, extension, password_hash FROM users WHERE id = ?", (user_id,))
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