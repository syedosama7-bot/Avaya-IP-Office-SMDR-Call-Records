import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'smdr_records.db')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM calls")
count = cursor.fetchone()[0]
print(f"Number of records in {DB_PATH}: {count}")
conn.close()