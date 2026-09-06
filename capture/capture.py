import mss
import pygetwindow as gw
import pytesseract
from PIL import Image
import time
import sys
import os

# Let this file import from the database folder
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db import init_db, save_snapshot

# If tesseract isn't auto-detected, uncomment and set your install path:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def get_active_window():
    try:
        window = gw.getActiveWindow()
        if window:
            return window.title
        return "Unknown"
    except Exception as e:
        return f"Error: {e}"

def take_screenshot(save_path="screenshot.png"):
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=save_path)
    return save_path

def extract_text(image_path):
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img)
    return text

def capture_and_save(session_id=1):
    """One full capture cycle: window + screenshot + OCR + save to DB."""
    title = get_active_window()
    path = take_screenshot("temp_screenshot.png")
    text = extract_text(path)
    timestamp = time.time()
    
    save_snapshot(session_id, title, text, timestamp)
    print(f"[{time.strftime('%H:%M:%S')}] Captured: {title}")

if __name__ == "__main__":
    init_db()
    print("Starting capture loop. Press Ctrl+C to stop.")
    
    MAX_CAPTURES = 20  # stop automatically after this many snapshots
    count = 0
    
    try:
        while count < MAX_CAPTURES:
            capture_and_save(session_id=1)
            count += 1
            time.sleep(15)
        print(f"\nReached {MAX_CAPTURES} captures. Stopping automatically.")
    except KeyboardInterrupt:
        print("\nCapture stopped manually.")