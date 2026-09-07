import sys, os, time, datetime
sys.path.append(os.path.dirname(__file__))
from database.db import init_db, save_snapshot

init_db()

yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
base = datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0, 0).timestamp()

# Simulates a scattered, heavily-interrupted day: short bursts, lots of switching
fake_yesterday = [
    (1, "Visual Studio Code", "working on feature branch", base + 0),
    (1, "Google Chrome", "checking email", base + 300),
    (1, "Visual Studio Code", "back to code", base + 600),
    (1, "Claude", "chat", base + 750),
    (1, "Visual Studio Code", "coding again", base + 1200),
    (1, "Google Chrome", "browsing", base + 1500),
    (1, "Visual Studio Code", "coding", base + 2100),
    (1, "File Explorer", "looking for files", base + 2400),
    (1, "Visual Studio Code", "coding", base + 3000),
]

for session_id, title, text, ts in fake_yesterday:
    save_snapshot(session_id, title, text, ts)

print("Yesterday's seed data inserted — a scattered, heavily-interrupted day for comparison.")