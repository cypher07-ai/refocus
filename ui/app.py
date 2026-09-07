import sys
import os
import time
import ctypes
import threading
import streamlit as st

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db import init_db, get_recent_snapshots
from capture.capture import capture_and_save
from sessions.session_engine import (
    detect_current_state,
    time_since_last_category,
    get_last_session_snapshots,
    get_previous_category,
    get_daily_stats,
)
from ai.briefing import generate_briefing_for_category
from ai.chat import chat_with_assistant

init_db()

# ---------- NATIVE WINDOWS IDLE DETECTION ----------
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds() -> float:
    last_input_info = LASTINPUTINFO()
    last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
        millis_since_boot = ctypes.windll.kernel32.GetTickCount()
        return max(0.0, (millis_since_boot - last_input_info.dwTime) / 1000.0)
    return 0.0

INACTIVITY_THRESHOLD = 180  # 3 minutes

if "capture_started" not in st.session_state:
    st.session_state.capture_started = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ---------- 3-MINUTE INACTIVITY CAPTURE LOOP ----------
def background_capture_loop(threshold_seconds=180, check_interval=5):
    snapshot_taken_for_idle = False
    while True:
        try:
            idle = get_idle_seconds()
            if idle < threshold_seconds:
                # User is active: reset snapshot flag
                snapshot_taken_for_idle = False
            else:
                # User has been inactive for >= 3 minutes
                if not snapshot_taken_for_idle:
                    print(f"💤 [Inactivity Detected: {int(idle)}s] Capturing snapshot...")
                    capture_and_save()
                    snapshot_taken_for_idle = True
        except Exception as e:
            print(f"[Capture error: {e}]")
        time.sleep(check_interval)


st.set_page_config(page_title="Refocus Copilot", page_icon="🧠", layout="centered")

# ---------- THEME / CSS ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown, .stMetric, .stButton {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: radial-gradient(circle at top left, #1a1440 0%, #0d0b1f 55%, #08070f 100%);
    color: #f0eefc;
}

h1 {
    font-weight: 800 !important;
    background: linear-gradient(90deg, #ff6ec4, #7873f5);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
}

[data-testid="stCaptionContainer"] {
    color: #a6a1c9 !important;
}

[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
}

[data-testid="stMetricLabel"] {
    color: #b8b3e0 !important;
    font-weight: 500 !important;
}

[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-weight: 700 !important;
}

.stButton > button {
    background: linear-gradient(90deg, #ff6ec4, #7873f5) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    padding: 0.6em 1.2em !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    box-shadow: 0 4px 15px rgba(120, 115, 245, 0.35);
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 22px rgba(255, 110, 196, 0.4);
}

[data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
}

hr {
    border-color: rgba(255,255,255,0.08) !important;
}

.stAlert {
    border-radius: 12px !important;
}

[data-testid="stChatMessage"] {
    background: rgba(255, 255, 255, 0.03);
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
""", unsafe_allow_html=True)

# ---------- HEADER ----------
st.title("🧠 Refocus Copilot")
st.caption("The 'where was I?' button for interrupted work — private, local AI, zero cloud.")

privacy_mode = st.toggle("🔒 Privacy Mode (pause tracking)", value=False)

if privacy_mode:
    st.info("Tracking paused. Your screen is not being captured.")
elif not st.session_state.capture_started:
    thread = threading.Thread(target=background_capture_loop, args=(INACTIVITY_THRESHOLD, 5), daemon=True)
    thread.start()
    st.session_state.capture_started = True

# ---------- LIVE INACTIVITY TIMER (AUTO-REFRESHES EVERY 1s) ----------
@st.fragment(run_every="1s")
def render_live_inactivity_widget():
    idle_secs = int(get_idle_seconds())
    
    col_a, col_b = st.columns([1, 1])
    if idle_secs < INACTIVITY_THRESHOLD:
        rem_secs = INACTIVITY_THRESHOLD - idle_secs
        rem_m, rem_s = rem_secs // 60, rem_secs % 60
        progress_val = min(1.0, idle_secs / INACTIVITY_THRESHOLD)
        with col_a:
            st.metric("Inactivity Status", "🟢 Active", f"Idle: {idle_secs}s")
        with col_b:
            st.metric("Snapshot In", f"{rem_m}m {rem_s}s", "threshold: 3m")
        st.progress(progress_val)
    else:
        away_m, away_s = idle_secs // 60, idle_secs % 60
        with col_a:
            st.metric("Inactivity Status", "💤 Interrupted", f"Away: {away_m}m {away_s}s", delta_color="inverse")
        with col_b:
            st.metric("Snapshot Status", "📸 Captured", "Saved to DB")
        st.progress(1.0)

render_live_inactivity_widget()

state = detect_current_state()

# ---------- LIVE STATE + RESUME ----------
if state.get("status") == "ok":
    previous_category = get_previous_category()

    if previous_category:
        away_seconds = time_since_last_category(previous_category)
        away_minutes = int(away_seconds) // 60
        away_secs_remainder = int(away_seconds) % 60

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Currently in", state['current_category'])
        with col2:
            st.metric(f"Away from {previous_category}", f"{away_minutes}m {away_secs_remainder}s")

        st.divider()

        if st.button(f"▶ Resume — where was I in {previous_category}?", type="primary", use_container_width=True):
            with st.spinner("Reconstructing context..."):
                briefing = generate_briefing_for_category(previous_category)
                snapshots = get_last_session_snapshots(previous_category)

            st.success("Here's your briefing:")
            st.markdown(briefing)

            with st.expander("See raw evidence (screenshots/OCR behind this answer)"):
                if snapshots:
                    for window_title, ocr_text, ts in snapshots:
                        st.text(f"[{window_title}]")
                        st.code(ocr_text[:500])
                else:
                    st.text("No snapshot evidence found for this session.")
    else:
        st.info("No interruption detected yet — keep working, then switch apps or step away to test Resume.")
else:
    st.warning("No session data found yet. Work for a bit, then refresh this page.")

# ---------- END OF DAY REPORT ----------
st.divider()
st.subheader("📊 End of Day Report")

today_stats = get_daily_stats(days_ago=0)
yesterday_stats = get_daily_stats(days_ago=1)

col1, col2, col3 = st.columns(3)

with col1:
    delta_score = round(today_stats["focus_score"] - yesterday_stats["focus_score"], 1)
    st.metric("Focus Score", f"{today_stats['focus_score']}%", delta=f"{delta_score}% vs yesterday")

with col2:
    delta_interruptions = today_stats["interruptions"] - yesterday_stats["interruptions"]
    st.metric("Interruptions", today_stats["interruptions"], delta=f"{delta_interruptions:+d} vs yesterday", delta_color="inverse")

with col3:
    focus_min_today = round(today_stats["focus_seconds"] / 60, 1)
    focus_min_yesterday = round(yesterday_stats["focus_seconds"] / 60, 1)
    delta_focus_min = round(focus_min_today - focus_min_yesterday, 1)
    st.metric("Focus Time", f"{focus_min_today} min", delta=f"{delta_focus_min:+.1f} min vs yesterday")

if today_stats["focus_score"] > yesterday_stats["focus_score"]:
    st.success(f"🔥 You're {delta_score:.0f}% more focused than yesterday. Keep it up!")
elif today_stats["total_snapshots"] > 0:
    st.warning("Today's focus score is lower than yesterday — more interruptions than usual.")

# ---------- CHAT WITH ASSISTANT ----------
st.divider()
st.subheader("💬 Ask Refocus")
st.caption("Ask about your focus habits, today's activity, or anything else.")

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_query = st.chat_input("Ask something, e.g. 'How focused was I today?'")

if user_query:
    st.session_state.chat_history.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = chat_with_assistant(st.session_state.chat_history)
        st.markdown(reply)

    st.session_state.chat_history.append({"role": "assistant", "content": reply})

st.divider()
st.caption("Refocus Copilot runs entirely locally. Nothing leaves your device.")