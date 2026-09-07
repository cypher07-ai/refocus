import sys
import os
import ollama

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from sessions.session_engine import detect_current_state, get_daily_stats


def chat_with_assistant(messages, model="llama3.2:3b"):
    """
    Sends a conversation to the local AI, with light context about
    the user's current activity so it can answer questions like
    'what have I been working on today?'
    """
    state = detect_current_state()
    today_stats = get_daily_stats(days_ago=0)

    context = (
        f"The user is currently in: {state.get('current_category', 'unknown')} "
        f"({state.get('current_window', 'unknown')}). "
        f"Today so far: {today_stats.get('interruptions', 0)} interruptions, "
        f"focus score {today_stats.get('focus_score', 0)}%."
    )

    system_prompt = {
        "role": "system",
        "content": (
            "You are the assistant inside Refocus Copilot, a focus-tracking app. "
            "Answer the user's questions about their work, focus habits, and productivity "
            "concisely and helpfully. " + context
        ),
    }

    full_messages = [system_prompt] + messages

    response = ollama.chat(model=model, messages=full_messages)
    return response["message"]["content"]


if __name__ == "__main__":
    reply = chat_with_assistant([{"role": "user", "content": "How focused have I been today?"}])
    print(reply)