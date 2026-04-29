from .database import get_db

def insert_call(call_data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO calls
        (call_start, duration_raw, duration_seconds, ring_time,
         caller, direction, called_num, dialled_num, account_code,
         is_internal, call_id, continuation, party1_device, party1_name,
         party2_device, party2_name, hold_time, park_time,
         auth_valid, auth_code, cost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', call_data)
    conn.commit()
    conn.close()

def fetch_calls(where_clause, params, limit=100):
    conn = get_db()
    cursor = conn.cursor()
    query = f"""
        SELECT id, call_start, duration_raw, ring_time, caller, direction,
               called_num, is_internal, party1_name, party2_name, hold_time, cost
        FROM calls
        {where_clause}
        ORDER BY id DESC
        LIMIT ?
    """
    cursor.execute(query, params + [limit])
    rows = cursor.fetchall()
    conn.close()
    return rows

def summary_stats(where_clause, params):
    conn = get_db()
    cursor = conn.cursor()
    query = f"""
        SELECT COUNT(*) as total_calls, SUM(duration_seconds) as total_seconds,
               AVG(duration_seconds) as avg_seconds, SUM(ring_time) as total_ring,
               SUM(hold_time) as total_hold, SUM(cost) as total_cost
        FROM calls {where_clause}
    """
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row

# You may add more specific query functions for reports here if desired,
# but for brevity we keep the generate_report logic in blueprints/reports.py using get_db().