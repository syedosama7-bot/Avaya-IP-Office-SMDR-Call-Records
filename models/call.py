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

def fetch_calls(where_clause, params, limit=20, offset=0):
    """Return a list of call rows (sqlite3.Row) with pagination."""
    conn = get_db()
    cursor = conn.cursor()
    query = f"""
        SELECT id, call_start, duration_raw, ring_time, caller, direction,
               called_num, is_internal, party1_name, party2_name, hold_time, cost,
               call_id
        FROM calls
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(query, params + [limit, offset])
    rows = cursor.fetchall()
    conn.close()
    return rows

def count_calls(where_clause, params):
    """Return total number of calls matching the filter."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM calls {where_clause}", params)
    count = cursor.fetchone()[0]
    conn.close()
    return count

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