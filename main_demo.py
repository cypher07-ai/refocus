import sys
import os
import time
import threading

sys.path.append(os.path.dirname(__file__))
from database.db import init_db
from capture.capture import capture_and_save
from sessions.session_engine import detect_current_state, calculate_total_away_time
from ai.briefing import generate_briefing_for_category

# Shared flag to stop the background thread cleanly
stop_capturing = threading.Event()

def background_capture_loop(interval_seconds=10):
    """Runs silently in the background, capturing every N seconds."""
    while not stop_capturing.is_set():
        try:
            capture_and_save(session_id=1)
        except Exception as e:
            print(f"[Capture error: {e}]")
        time.sleep(interval_seconds)

def main():
    init_db()
    
    print("=" * 50)
    print("REFOCUS COPILOT - LIVE DEMO MODE")
    print("=" * 50)
    print("Background capture starting now (every 10 seconds).")
    print("Work normally, switch windows, get 'interrupted'.")
    print()
    print("Press ENTER at any time to simulate hitting RESUME.")
    print("Type 'quit' + ENTER to stop everything.")
    print("=" * 50)
    
    # Start capture in a background thread
    capture_thread = threading.Thread(target=background_capture_loop, args=(10,), daemon=True)
    capture_thread.start()
    
    while True:
        user_input = input()
        
        if user_input.strip().lower() == "quit":
            print("Stopping...")
            stop_capturing.set()
            break
        
        # ENTER pressed - simulate Resume
        print("\n--- RESUME PRESSED ---")
        state = detect_current_state()
        print(f"Current window: {state.get('current_window', 'unknown')}")
        print(f"Current category: {state.get('current_category', 'unknown')}")
        
        away_time = calculate_total_away_time("coding")
        print(f"Estimated time away from coding: {away_time} seconds")
        
        print("\nGenerating AI briefing...\n")
        briefing = generate_briefing_for_category("coding")
        print(briefing)
        print("\n--- Back to work. Press ENTER again anytime. ---\n")

if __name__ == "__main__":
    main()