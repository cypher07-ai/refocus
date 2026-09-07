import sys
import os
import time as time_module
import datetime

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


def get_day_bounds(days_ago=0):
    now = datetime.datetime.now()
    target_day = now - datetime.timedelta(days=days_ago)
    start = datetime.datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0)
    end = start + datetime.timedelta(days=1)
    return start.timestamp(), end.timestamp()


def get_daily_stats(days_ago=0, limit=2000):
    start_ts, end_ts = get_day_bounds(days_ago)
    all_snaps = get_recent_snapshots(limit)
    day_snaps = [s for s in all_snaps if start_ts <= s[2] < end_ts]
    day_snaps = list(reversed(day_snaps))
    if not day_snaps:
        return {"total_snapshots": 0, "focus_seconds": 0, "interruptions": 0, "focus_score": 0, "total_seconds": 0}
    focus_seconds = 0
    interruptions = 0
    last_cat = None
    last_ts = None
    for window_title, ocr_text, ts in day_snaps:
        cat = categorize_window(window_title)
        if last_ts is not None:
            gap = ts - last_ts
            if last_cat == "coding":
                focus_seconds += gap
            if cat != last_cat:
                interruptions += 1
        last_cat = cat
        last_ts = ts
    total_seconds = day_snaps[-1][2] - day_snaps[0][2]
    focus_score = round((focus_seconds / total_seconds) * 100, 1) if total_seconds > 0 else 0
    return {
        "total_snapshots": len(day_snaps),
        "focus_seconds": round(focus_seconds, 1),
        "interruptions": interruptions,
        "focus_score": focus_score,
        "total_seconds": round(total_seconds, 1),
    }


if __name__ == "__main__":
    state = detect_current_state()
    print(state)
    away = calculate_total_away_time("coding")
    print(f"Time away from 'coding': {away} seconds")
def get_weekly_summary():
    """Compiles aggregated performance across the last 7 days."""
    days = []
    total_focus_sec = 0
    total_switches = 0
    day_scores = []
    
    for i in range(6, -1, -1):
        stats = get_daily_stats(days_ago=i)
        day_date = datetime.datetime.now() - datetime.timedelta(days=i)
        day_label = day_date.strftime("%a (%b %d)")
        
        focus_mins = round(stats["focus_seconds"] / 60, 1)
        score = stats["focus_score"]
        switches = stats["interruptions"]
        
        total_focus_sec += stats["focus_seconds"]
        total_switches += switches
        if score > 0:
            day_scores.append(score)
            
        days.append({
            "day": day_label,
            "short_day": day_date.strftime("%a"),
            "focus_mins": focus_mins,
            "focus_hours": round(focus_mins / 60, 1),
            "score": score,
            "interruptions": switches
        })
        
    avg_score = round(sum(day_scores) / len(day_scores), 1) if day_scores else 0
    total_focus_hours = round(total_focus_sec / 3600, 1)
    
    # Identify most productive day
    best_day = max(days, key=lambda d: d["focus_mins"]) if days else None
    
    return {
        "days": days,
        "avg_focus_score": avg_score,
        "total_focus_hours": total_focus_hours,
        "total_interruptions": total_switches,
        "best_day": best_day["day"] if best_day else "N/A",
        "best_day_hours": best_day["focus_hours"] if best_day else 0
    }