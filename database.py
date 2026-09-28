import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("Database:", DB_PATH)

# =========================
# USERS TABLE
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email TEXT UNIQUE,
    password TEXT,
    email_otp TEXT,
    is_verified INTEGER DEFAULT 0,
    reset_otp TEXT,
    reset_otp_expiry TEXT,
    reset_otp_attempts INTEGER DEFAULT 0
)
""")

# =========================
# CHECK EXISTING USERS COLUMNS
# =========================

cursor.execute("PRAGMA table_info(users)")
existing_columns = [row[1] for row in cursor.fetchall()]

print("\nExisting users columns:")
print(existing_columns)

# =========================
# ADD MISSING COLUMNS
# =========================

if "email" not in existing_columns:
    cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")

if "email_otp" not in existing_columns:
    cursor.execute("ALTER TABLE users ADD COLUMN email_otp TEXT")

if "is_verified" not in existing_columns:
    cursor.execute(
        "ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0"
    )

if "reset_otp" not in existing_columns:
    cursor.execute("ALTER TABLE users ADD COLUMN reset_otp TEXT")

if "reset_otp_expiry" not in existing_columns:
    cursor.execute(
        "ALTER TABLE users ADD COLUMN reset_otp_expiry TEXT"
    )

if "reset_otp_attempts" not in existing_columns:
    cursor.execute(
        "ALTER TABLE users ADD COLUMN reset_otp_attempts INTEGER DEFAULT 0"
    )

# =========================
# EXPENSES
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    amount REAL,
    category TEXT,
    note TEXT
)
""")

# =========================
# CATEGORIES
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(user_id, name),
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# =========================
# LOGS
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    event TEXT NOT NULL,
    details TEXT,
    ip TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

conn.commit()

# =========================
# DEFAULT CATEGORIES
# =========================

default_categories = [
    "Food",
    "Travel",
    "EMI",
    "Subscription",
    "Shopping",
    "Bills",
    "Health",
    "Education",
    "Other"
]

cursor.execute("SELECT id FROM users")
users = cursor.fetchall()

for user in users:
    user_id = user[0]

    for category in default_categories:
        cursor.execute("""
            INSERT OR IGNORE INTO categories (user_id, name)
            VALUES (?, ?)
        """, (user_id, category))

conn.commit()

# =========================
# FINAL CHECK
# =========================

print("\nFinal users columns:")

cursor.execute("PRAGMA table_info(users)")

for column in cursor.fetchall():
    print(column)

print("\nTables:")

cursor.execute("""
SELECT name
FROM sqlite_master
WHERE type='table'
ORDER BY name
""")

for table in cursor.fetchall():
    print("✅", table[0])

conn.close()

print("\n✅ DATABASE MIGRATION COMPLETED!")