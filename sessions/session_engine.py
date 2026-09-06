import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db import get_recent_snapshots

# Simple category mapping - expand this list as needed for your demo apps
CATEGORY_MAP = {
    "Visual Studio Code": "coding",
    "Windows PowerShell": "coding",
    "Google Chrome": "browsing",
    "Claude": "browsing",
    "File Explorer": "files",
}

def categorize_window(window_title):
    """Roughly categorizes a window title into a task category."""
    for keyword, category in CATEGORY_MAP.items():
        if keyword.lower() in window_title.lower():
            return category
    return "other"

def detect_current_state(limit=10):
    """
    Looks at recent snapshots and determines:
    - what category the user is currently in
    - whether this looks like a fresh interruption (category just changed)
    """
    snapshots = get_recent_snapshots(limit)
    if not snapshots:
        return {"status": "no_data"}

    snapshots = list(snapshots)
    current_title, current_ocr, current_ts = snapshots[0]
    current_category = categorize_window(current_title)

    streak_start_ts = current_ts
    for window_title, ocr_text, ts in snapshots[1:]:
        if categorize_window(window_title) == current_category:
            streak_start_ts = ts
        else:
            break

    time_in_current = current_ts - streak_start_ts

    return {
        "status": "ok",
        "current_window": current_title,
        "current_category": current_category,
        "time_in_current_seconds": round(time_in_current, 1),
        "last_snapshot_time": current_ts,
    }

def calculate_total_away_time(category_to_track, limit=50):
    """
    Estimates total time spent away from a specific category
    across recent snapshots - used for the 'interruption cost' stat.
    """
    snapshots = get_recent_snapshots(limit)
    if not snapshots:
        return 0

    snapshots = list(reversed(snapshots))  # oldest first
    away_seconds = 0
    last_ts = None

    for window_title, ocr_text, ts in snapshots:
        category = categorize_window(window_title)
        if last_ts is not None:
            gap = ts - last_ts
            if category != category_to_track:
                away_seconds += gap
        last_ts = ts

    return round(away_seconds, 1)

if __name__ == "__main__":
    state = detect_current_state()
    print(state)

    away = calculate_total_away_time("coding")
    print(f"Time away from 'coding': {away} seconds")
def get_last_session_snapshots(target_category, limit=50):
    """
    Finds the most recent contiguous block of snapshots belonging to
    target_category, BEFORE the user switched away from it.
    This is what powers the 'Resume' briefing - not just the last N snapshots,
    but specifically the session that got interrupted.
    """
    snapshots = get_recent_snapshots(limit)
    if not snapshots:
        return []

    # snapshots come back newest-first
    snapshots = list(snapshots)

    # Step 1: skip forward past any snapshots that are NOT target_category
    # (i.e. skip the current interruption itself)
    idx = 0
    while idx < len(snapshots) and categorize_window(snapshots[idx][0]) != target_category:
        idx += 1

    if idx == len(snapshots):
        return []  # never found this category in recent history

    # Step 2: collect the contiguous run of target_category snapshots from here
    session_snapshots = []
    while idx < len(snapshots) and categorize_window(snapshots[idx][0]) == target_category:
        session_snapshots.append(snapshots[idx])
        idx += 1

    return list(reversed(session_snapshots))  # oldest first, readable order