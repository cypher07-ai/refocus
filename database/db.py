import sqlite3

def get_latest_session():
    conn = sqlite3.connect("refocus.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, app_category, started_at, ended_at FROM sessions ORDER BY id DESC LIMIT 1")
    session = cursor.fetchone()
    conn.close()
    return session  # (id, app_category, started_at, ended_at)

def get_snapshots_for_session(session_id):
    conn = sqlite3.connect("refocus.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT window_title, ocr_text, timestamp
        FROM snapshots
        WHERE session_id = ?
        ORDER BY timestamp ASC
    """, (session_id,))
    snapshots = cursor.fetchall()
    conn.close()
    return snapshots  # list of (window_title, ocr_text, timestamp)