import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "refocus.db")

def init_db():
    """Creates the database and tables if they don't already exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
    
    conn.commit()
    conn.close()
    print(f"Database ready at: {DB_PATH}")

def save_snapshot(session_id, window_title, ocr_text, timestamp):
    """Saves one captured snapshot into the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO snapshots (session_id, window_title, ocr_text, timestamp)
        VALUES (?, ?, ?, ?)
    """, (session_id, window_title, ocr_text, timestamp))
    conn.commit()
    conn.close()

def get_recent_snapshots(limit=5):
    """Fetches the most recent snapshots, newest first."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT window_title, ocr_text, timestamp
        FROM snapshots
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")