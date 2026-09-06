import streamlit as st
import time
from database.db import get_latest_session, get_snapshots_for_session
from ai.briefing import generate_briefing

st.set_page_config(page_title="ReFocus")

st.title("ReFocus")
st.caption("The 'where was I?' button for interrupted work")

# Get the latest session from the database
session = get_latest_session()

if session:
    session_id, app_category, started_at, ended_at = session
    away_seconds = int(time.time() - ended_at)
    away_minutes = away_seconds // 60
    away_secs_remainder = away_seconds % 60

    st.metric(
        label=f"⏱️ Time away from '{app_category}'",
        value=f"{away_minutes} min {away_secs_remainder} sec"
    )

    st.divider()

    if st.button("▶️ Resume — where was I?", type="primary"):
        with st.spinner("Reconstructing context..."):
            snapshots = get_snapshots_for_session(session_id)
            briefing = generate_briefing(snapshots)
        st.success("Here's your briefing:")
        st.markdown(briefing)

        with st.expander("See raw evidence (screenshots/OCR behind this answer)"):
            for window_title, ocr_text, ts in snapshots:
                st.text(f"[{window_title}]")
                st.code(ocr_text)
else:
    st.warning("No session data found. Run the seed script first.")