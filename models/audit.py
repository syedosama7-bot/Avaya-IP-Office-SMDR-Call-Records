from .database import get_db
from datetime import datetime
from flask import request
from models.database import get_db
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
    conn.close()