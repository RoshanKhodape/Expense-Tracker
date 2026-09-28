import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")

print("Checking database:")
print(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
SELECT name
FROM sqlite_master
WHERE type='table'
ORDER BY name
""")

tables = cur.fetchall()

print("\nTables:")
for table in tables:
    print("✅", table[0])

print("\nUsers columns:")

cur.execute("PRAGMA table_info(users)")
columns = cur.fetchall()

for column in columns:
    print(column)

conn.close()