import os
import sqlite3
import time
from pathlib import Path
import mss
import pygetwindow as gw
import pytesseract
from PIL import Image

# Always points to refocus.db in project root
DB_PATH = Path(__file__).resolve().parent.parent / "refocus.db"

# Optional: set Tesseract path if needed
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

_mss_factory = getattr(mss, "MSS", mss.mss)

def get_active_window_info() -> tuple[str, str]:
    """Returns (window_title, app_category)."""
    try:
        active_win = gw.getActiveWindow()
        if active_win and active_win.title.strip():
            title = active_win.title.strip()
            app_category = title.split(" - ")[-1] if " - " in title else title
            return title, app_category
    except Exception:
        pass
    return "Desktop / Idle", "General"

def capture_and_save(session_id: int = None) -> dict:
    """
    Captures active window screenshot, performs OCR, and saves snapshot to refocus.db.
    Used by your UI and tracker.
    """
    title, category = get_active_window_info()
    now = time.time()
    
    # 1. Capture screen
    try:
        with _mss_factory() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            
        try:
            ocr_text = pytesseract.image_to_string(img)
        except Exception as e:
            ocr_text = f"[OCR unavailable: {e}]"
    except Exception as e:
        ocr_text = f"[Capture error: {e}]"

    # 2. Save to SQLite database
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # If no session_id provided, get or create the latest session
        if session_id is None:
            cursor.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                session_id = row[0]
                cursor.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (now, session_id))
            else:
                cursor.execute("INSERT INTO sessions (app_category, started_at, ended_at) VALUES (?, ?, ?)",
                               (category, now - 60, now))
                session_id = cursor.lastrowid

        # Insert snapshot
        cursor.execute("""
            INSERT INTO snapshots (session_id, window_title, ocr_text, timestamp)
            VALUES (?, ?, ?, ?)
        """, (session_id, title, ocr_text, now))
        conn.commit()

    return {
        "session_id": session_id,
        "window_title": title,
        "app_category": category,
        "ocr_text": ocr_text,
        "timestamp": now
    }