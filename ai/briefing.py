import sys
import os
import ollama

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db import get_recent_snapshots

def clean_snapshot_text(text, max_chars=400):
    """Trims noisy OCR text down to a manageable size."""
    return text.strip()[:max_chars]

def generate_briefing(limit=5):
    """Pulls recent snapshots and asks the local AI to summarize them."""
    snapshots = get_recent_snapshots(limit)
    
    if not snapshots:
        return "No recent activity found."
    
    # Build context string from snapshots (oldest to newest reads better)
    snapshots = list(reversed(snapshots))
    context_parts = []
    for window_title, ocr_text, timestamp in snapshots:
        cleaned = clean_snapshot_text(ocr_text)
        context_parts.append(f"Window: {window_title}\nContent snippet: {cleaned}")
    
    context = "\n---\n".join(context_parts)
    
    prompt = f"""You are helping someone resume interrupted work. Based on these screen snapshots (oldest to newest), write a short recovery briefing with exactly three parts:

CONFIRMED: (1 sentence - what app/window they were last actively using)
LIKELY: (1 sentence - what task they were probably doing, based on the content)
SUGGESTED NEXT STEP: (1 sentence - a reasonable next action)

If there isn't enough information, say so honestly instead of guessing.

Snapshots:
{context}"""

    response = ollama.chat(model='llama3.2:3b', messages=[
        {"role": "user", "content": prompt}
    ])
    
    return response['message']['content']

if __name__ == "__main__":
    print("Generating briefing from recent activity...\n")
    briefing = generate_briefing(limit=5)
    print(briefing)