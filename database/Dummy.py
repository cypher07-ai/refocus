import sqlite3
import time

conn = sqlite3.connect("refocus.db")
cursor = conn.cursor()

# Create tables (matches the schema you and Person A agreed on)
cursor.execute("""
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_category TEXT,
    started_at REAL,
    ended_at REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    window_title TEXT,
    ocr_text TEXT,
    timestamp REAL
)
""")

# Insert one fake session: "you were coding 10 minutes ago"
now = time.time()
session_start = now - 900   # 15 min ago
session_end = now - 400     # 6.5 min ago (this is when the "interruption" happened)

cursor.execute("""
INSERT INTO sessions (app_category, started_at, ended_at)
VALUES (?, ?, ?)
""", ("VSCode", session_start, session_end))

session_id = cursor.lastrowid

# Insert a few fake snapshots within that session
fake_snapshots = [
    ("VSCode - auth_service.py", "def verify_token(token):\n    # TODO: check expiry\n    payload = decode(token)", session_start + 100),
    ("VSCode - auth_service.py", "Error: TokenExpiredError at line 42\nTraceback...", session_start + 300),
    ("Chrome - JWT.io debugger", "Decoded payload: {exp: 1699999999, sub: user123}", session_end - 50),
]

for title, text, ts in fake_snapshots:
    cursor.execute("""
    INSERT INTO snapshots (session_id, window_title, ocr_text, timestamp)
    VALUES (?, ?, ?, ?)
    """, (session_id, title, text, ts))

conn.commit()
conn.close()

print("Dummy database seeded successfully as refocus.db")