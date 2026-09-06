import sys
import os
import ollama

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db import get_recent_snapshots
from sessions.session_engine import get_last_session_snapshots, categorize_window

def clean_snapshot_text(text, max_chars=400):
    return text.strip()[:max_chars]

def build_context(snapshots):
    context_parts = []
    for window_title, ocr_text, timestamp in snapshots:
        cleaned = clean_snapshot_text(ocr_text)
        context_parts.append(f"Window: {window_title}\nContent snippet: {cleaned}")
    return "\n---\n".join(context_parts)

def generate_briefing_for_category(target_category, model="llama3.2:3b"):
    """
    Generates a Resume briefing specifically for the last session
    that matched target_category, before the user got interrupted.
    """
    snapshots = get_last_session_snapshots(target_category)

    if not snapshots:
        return "I couldn't confidently determine what you were working on. Not enough recent activity found for this category."

    context = build_context(snapshots)

    prompt = f"""You are helping someone resume interrupted work. Based on these screen snapshots (oldest to newest, all from the same work session), write a short recovery briefing with exactly three parts:

CONFIRMED: (1 sentence - what app/window they were last actively using, based only on what's visible)
LIKELY: (1 sentence - what task they were probably doing, based on the content)
SUGGESTED NEXT STEP: (1 sentence - a reasonable next action)

If there isn't enough information to be confident, say so honestly instead of guessing.

Snapshots:
{context}"""

    response = ollama.chat(model=model, messages=[
        {"role": "user", "content": prompt}
    ])

    return response['message']['content']

if __name__ == "__main__":
    print("Generating briefing for 'coding' session...\n")
    briefing = generate_briefing_for_category("coding")
    print(briefing)