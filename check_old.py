import sqlite3
conn = sqlite3.connect('smdr_records.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM calls WHERE call_start < '2026/04/27 00:00:00'")
count = cursor.fetchone()[0]
print(f"Records before today: {count}")
conn.close()