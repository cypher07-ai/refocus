def generate_briefing(snapshots):
    """
    Placeholder version — hardcoded logic based on dummy data.
    Person A will replace this with a real Ollama call later,
    but the function signature (input: snapshots, output: string) stays the same.
    """
    if not snapshots:
        return "No recent activity found."

    last_window = snapshots[-1][0]
    last_text = snapshots[-1][1]

    briefing = f"""
**What you were working on:** Debugging the auth flow in `auth_service.py`

**Last thing you did:** You hit a `TokenExpiredError` and had just opened {last_window} to inspect the decoded token payload.

**Suggested next step:** Check the token expiry logic — the payload shows `exp: 1699999999`, likely already past current time.
"""
    return briefing