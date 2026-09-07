import sys, os, time
sys.path.append(os.path.dirname(__file__))
from database.db import init_db, save_snapshot

init_db()

now = time.time()
fake_data = [
    (1, "Visual Studio Code", "def login(): token = validate_jwt(request.headers['Authorization']) if not token: raise 401Unauthorized", now - 300),
    (1, "Visual Studio Code", "Debugging JWT validation, checking expiry logic in auth.py", now - 240),
    (1, "Windows PowerShell", "Traceback: 401 Unauthorized - token expired", now - 180),
    (1, "Google Chrome", "JWT.io - JSON Web Token Debugger", now - 60),
]

for session_id, title, text, ts in fake_data:
    save_snapshot(session_id, title, text, ts)

print("Seed data inserted.")