from .database import get_db

def get_tariffs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT prefix, rate_per_minute FROM tariffs")
    rows = cursor.fetchall()
    conn.close()
    return rows