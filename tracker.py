import ctypes
import os
import sqlite3
import time
from pathlib import Path
import mss
import pygetwindow as gw
import pytesseract
from PIL import Image

INACTIVITY_THRESHOLD_SECONDS = 180  # 3 minutes
CHECK_INTERVAL_SECONDS = 5          # Check every 5s

DB_PATH = Path(__file__).resolve().parent / "refocus.db"
_mss_factory = getattr(mss, "MSS", mss.mss)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, app_category TEXT, started_at REAL, ended_at REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, window_title TEXT, ocr_text TEXT, timestamp REAL, FOREIGN KEY(session_id) REFERENCES sessions(id))")
        conn.commit()

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds() -> float:
    last_input_info = LASTINPUTINFO()
    last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
        millis_since_boot = ctypes.windll.kernel32.GetTickCount()
        return max(0.0, (millis_since_boot - last_input_info.dwTime) / 1000.0)
    return 0.0

def get_active_window_info():
    try:
        active_win = gw.getActiveWindow()
        if active_win and active_win.title.strip():
            title = active_win.title.strip()
            category = title.split(" - ")[-1] if " - " in title else title
            return title, category
    except Exception:
        pass
    return "Desktop / Idle", "General"

def take_single_snapshot():
    title, category = get_active_window_info()
    try:
        with _mss_factory() as sct:
            monitor = sct.monitors[1]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        try:
            ocr_text = pytesseract.image_to_string(img)
        except Exception as e:
            ocr_text = f"[OCR error: {e}]"
    except Exception as e:
        ocr_text = f"[Capture error: {e}]"
    return {"window_title": title, "app_category": category, "ocr_text": ocr_text}

def run_inactivity_tracker():
    init_db()
    print("==================================================")
    print("🎯 ReFocus Inactivity Tracker Running")
    print(f"⏱️  Threshold: {INACTIVITY_THRESHOLD_SECONDS // 60} minutes ({INACTIVITY_THRESHOLD_SECONDS}s)")
    print("==================================================\n")

    current_session_id = None
    last_known_active_time = time.time()
    snapshot_taken = False

    try:
        while True:
            idle_seconds = int(get_idle_seconds())
            now = time.time()
            title, category = get_active_window_info()

            if idle_seconds < INACTIVITY_THRESHOLD_SECONDS:
                # User is active
                last_known_active_time = now - idle_seconds
                if snapshot_taken:
                    print(f"\n👋 User returned! Starting new active session for '{category}'.")
                    snapshot_taken = False
                    current_session_id = None

                print(f"\r🟢 Active | Current Window: {title[:30]} | Idle: {idle_seconds}s / {INACTIVITY_THRESHOLD_SECONDS}s   ", end="", flush=True)

                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    if current_session_id is None:
                        cursor.execute("INSERT INTO sessions (app_category, started_at, ended_at) VALUES (?, ?, ?)",
                                       (category, last_known_active_time, last_known_active_time))
                        current_session_id = cursor.lastrowid
                    else:
                        cursor.execute("UPDATE sessions SET ended_at = ?, app_category = ? WHERE id = ?",
                                       (last_known_active_time, category, current_session_id))
                    conn.commit()

            else:
                # User is inactive for 3+ minutes
                if not snapshot_taken:
                    print(f"\n\n📸 [SNAPSHOT TRIGGERED] Inactive for {idle_seconds}s (>= {INACTIVITY_THRESHOLD_SECONDS}s)!")
                    data = take_single_snapshot()
                    session_end_time = now - idle_seconds

                    with sqlite3.connect(DB_PATH) as conn:
                        cursor = conn.cursor()
                        if current_session_id:
                            cursor.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (session_end_time, current_session_id))
                        else:
                            cursor.execute("INSERT INTO sessions (app_category, started_at, ended_at) VALUES (?, ?, ?)",
                                           (data["app_category"], session_end_time - 60, session_end_time))
                            current_session_id = cursor.lastrowid

                        cursor.execute("INSERT INTO snapshots (session_id, window_title, ocr_text, timestamp) VALUES (?, ?, ?, ?)",
                                       (current_session_id, data["window_title"], data["ocr_text"], session_end_time))
                        conn.commit()

                    print(f"✅ Saved snapshot for '{data['window_title']}' to database.")
                    print("😴 Pausing further captures until you touch mouse/keyboard.\n")
                    snapshot_taken = True
                else:
                    print(f"\r💤 Away ({idle_seconds}s) — snapshot already taken. Waiting for user return...   ", end="", flush=True)

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n\n🛑 Tracker stopped.")

if __name__ == "__main__":
    run_inactivity_tracker()