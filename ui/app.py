import sys
import os
import time
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
)
from ai.briefing import generate_briefing_for_category

init_db()

#st.markdown("<meta http-equiv='refresh' content='5'>", unsafe_allow_html=True)

if "capture_started" not in st.session_state:
    st.session_state.capture_started = False


def background_capture_loop(interval_seconds=10):
    while True:
        try:
            capture_and_save(session_id=1)
        except Exception as e:
            print(f"[Capture error: {e}]")
        time.sleep(interval_seconds)


st.set_page_config(page_title="Refocus Copilot")
st.title("🧠 Refocus Copilot")
st.caption("The 'where was I?' button for interrupted work")

privacy_mode = st.toggle("🔒 Privacy Mode (pause tracking)", value=False)

if privacy_mode:
    st.info("Tracking paused. Your screen is not being captured.")
elif not st.session_state.capture_started:
    thread = threading.Thread(target=background_capture_loop, args=(10,), daemon=True)
    thread.start()
    st.session_state.capture_started = True

state = detect_current_state()

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
        st.info("No interruption detected yet — keep working, then switch apps to test Resume.")
else:
    st.warning("No session data found yet. Work for a bit, then refresh this page.")

st.divider()
st.caption("Refocus Copilot runs entirely locally. Nothing leaves your device.")