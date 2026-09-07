import sys
import os
import time as time_module

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db import get_recent_snapshots

CATEGORY_MAP = {
    "Visual Studio Code": "coding",
    "Windows PowerShell": "coding",
    "Google Chrome": "browsing",
    "Claude": "browsing",
    "File Explorer": "files",
}


def categorize_window(window_title):
    for keyword, category in CATEGORY_MAP.items():
        if keyword.lower() in window_title.lower():
            return category
    return "other"


def detect_current_state(limit=10):
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
    snapshots = get_recent_snapshots(limit)
    if not snapshots:
        return 0

    snapshots = list(reversed(snapshots))
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


def time_since_last_category(category, limit=50):
    snapshots = get_recent_snapshots(limit)
    if not snapshots:
        return 0

    now = time_module.time()

    for window_title, ocr_text, ts in snapshots:
        if categorize_window(window_title) == category:
            return round(now - ts, 1)

    return 0


def get_last_session_snapshots(target_category, limit=50):
    snapshots = get_recent_snapshots(limit)
    if not snapshots:
        return []

    snapshots = list(snapshots)

    idx = 0
    while idx < len(snapshots) and categorize_window(snapshots[idx][0]) != target_category:
        idx += 1

    if idx == len(snapshots):
        return []

    session_snapshots = []
    while idx < len(snapshots) and categorize_window(snapshots[idx][0]) == target_category:
        session_snapshots.append(snapshots[idx])
        idx += 1

    return list(reversed(session_snapshots))


def get_previous_category(limit=50):
    snapshots = get_recent_snapshots(limit)
    if not snapshots or len(snapshots) < 2:
        return None

    current_category = categorize_window(snapshots[0][0])

    for window_title, ocr_text, ts in snapshots[1:]:
        cat = categorize_window(window_title)
        if cat != current_category:
            return cat

    return None


if __name__ == "__main__":
    state = detect_current_state()
    print(state)

    away = calculate_total_away_time("coding")
    print(f"Time away from 'coding': {away} seconds")