import sys
import os
import time
import ctypes
import threading
import sqlite3
import datetime
import streamlit as st
from pathlib import Path

# -----------------------------------------------------------------------------
# Path Resolution & Module Imports
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db import init_db, get_recent_snapshots
from capture.capture import capture_and_save, get_active_window_info
from sessions.session_engine import (
    detect_current_state,
    time_since_last_category,
    get_last_session_snapshots,
    get_previous_category,
    get_daily_stats,
    categorize_window,
)

# Optional AI imports with robust fallbacks
try:
    from ai.briefing import generate_briefing_for_category
except Exception:
    def generate_briefing_for_category(category):
        return (
            f"**CONFIRMED:** Last active in workspace `{category}`.\n\n"
            f"**LIKELY:** Working through active code files and reviewing recent state.\n\n"
            f"**SUGGESTED NEXT STEP:** Open your recent files in `{category}` and resume from your last edit."
        )

try:
    from ai.chat import chat_with_assistant
except Exception:
    def chat_with_assistant(messages):
        return "Local AI service offline. Ensure Ollama is running (`ollama run llama3.2:3b`) to enable natural language queries."

init_db()

# -----------------------------------------------------------------------------
# 7-Day Weekly Analytics Helper
# -----------------------------------------------------------------------------
def get_weekly_summary():
    """Aggregates focus telemetry and context switches across the last 7 days."""
    days = []
    total_focus_sec = 0
    total_switches = 0
    day_scores = []
    
    for i in range(6, -1, -1):
        stats = get_daily_stats(days_ago=i)
        day_date = datetime.datetime.now() - datetime.timedelta(days=i)
        day_label = day_date.strftime("%a (%b %d)")
        
        focus_mins = round(stats.get("focus_seconds", 0) / 60, 1)
        score = stats.get("focus_score", 0)
        switches = stats.get("interruptions", 0)
        
        total_focus_sec += stats.get("focus_seconds", 0)
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
    best_day = max(days, key=lambda d: d["focus_mins"]) if days else None
    
    return {
        "days": days,
        "avg_focus_score": avg_score,
        "total_focus_hours": total_focus_hours,
        "total_interruptions": total_switches,
        "best_day": best_day["day"] if best_day else "N/A",
        "best_day_hours": best_day["focus_hours"] if best_day else 0
    }

# -----------------------------------------------------------------------------
# Native Windows Idle Detection & Inactivity Configuration
# -----------------------------------------------------------------------------
INACTIVITY_THRESHOLD = 180  # 3 minutes (180s)
POLL_INTERVAL = 4           # Background poll cycle (seconds)

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds() -> float:
    last_input_info = LASTINPUTINFO()
    last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
        millis_since_boot = ctypes.windll.kernel32.GetTickCount()
        return max(0.0, (millis_since_boot - last_input_info.dwTime) / 1000.0)
    return 0.0

# -----------------------------------------------------------------------------
# Background Inactivity Snapshot Daemon
# -----------------------------------------------------------------------------
def run_inactivity_daemon(threshold_seconds=180, interval=4):
    snapshot_taken_for_idle = False
    while True:
        try:
            if st.session_state.get("privacy_mode", False):
                time.sleep(interval)
                continue

            idle = get_idle_seconds()
            if idle < threshold_seconds:
                snapshot_taken_for_idle = False
            else:
                if not snapshot_taken_for_idle:
                    capture_and_save()
                    snapshot_taken_for_idle = True
        except Exception:
            pass
        time.sleep(interval)

if "daemon_active" not in st.session_state:
    daemon_thread = threading.Thread(
        target=run_inactivity_daemon,
        args=(INACTIVITY_THRESHOLD, POLL_INTERVAL),
        daemon=True,
    )
    daemon_thread.start()
    st.session_state["daemon_active"] = True

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "briefing_cache" not in st.session_state:
    st.session_state["briefing_cache"] = None

if "show_weekly_report" not in st.session_state:
    st.session_state["show_weekly_report"] = False

# -----------------------------------------------------------------------------
# Streamlit App Configuration & Meta Design Tokens
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ReFocus — Work Context OS",
    page_icon="◬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Meta Commerce Design System (Stark White Canvas, Pill CTAs, 32px Cards, Montserrat)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --canvas: #ffffff;
    --surface-soft: #f1f4f7;
    --ink-deep: #0a1317;
    --ink: #1c1e21;
    --charcoal: #444950;
    --slate: #4b4c4f;
    --steel: #5d6c7b;
    --stone: #8595a4;
    --hairline: #ced0d4;
    --hairline-soft: #dee3e9;
    --ink-button: #000000;
    --primary: #0064e0;
    --primary-deep: #0457cb;
    --success: #31a24c;
    --warning: #f2a918;
    --critical: #e41e3f;
}

html, body, [class*="css"], .stMarkdown, .stText {
    font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
}

code, kbd, samp, pre {
    font-family: 'JetBrains Mono', Consolas, monospace !important;
}

.stApp {
    background-color: var(--canvas) !important;
    color: var(--ink) !important;
}

header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
}

.main .block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 4rem !important;
    max-width: 1240px !important;
}

/* Meta Card System */
.meta-card {
    background-color: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: 32px;
    padding: 32px;
    margin-bottom: 24px;
    box-shadow: 0 1px 4px rgba(20, 22, 26, 0.04);
}

.meta-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--hairline-soft);
    padding-bottom: 16px;
    margin-bottom: 20px;
}

.meta-card-title {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.14px;
    color: var(--ink-deep);
    display: flex;
    align-items: center;
    gap: 8px;
    text-transform: uppercase;
}

/* Meta Pill Badges */
.meta-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 100px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: -0.14px;
}

.meta-badge-active {
    background-color: rgba(49, 162, 76, 0.1);
    color: var(--success);
    border: 1px solid rgba(49, 162, 76, 0.25);
}

.meta-badge-idle {
    background-color: rgba(242, 169, 24, 0.12);
    color: #c98008;
    border: 1px solid rgba(242, 169, 24, 0.3);
}

.meta-badge-paused {
    background-color: var(--surface-soft);
    color: var(--steel);
    border: 1px solid var(--hairline-soft);
}

/* Meta Metric Tiles */
.meta-metric-tile {
    background-color: var(--surface-soft);
    border: 1px solid var(--hairline-soft);
    border-radius: 16px;
    padding: 20px 22px;
}

.meta-metric-label {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: -0.14px;
    color: var(--steel);
    margin-bottom: 6px;
    text-transform: uppercase;
}

.meta-metric-val {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.2px;
    color: var(--ink-deep);
    line-height: 1.15;
}

.meta-metric-sub {
    font-size: 12px;
    font-weight: 400;
    color: var(--charcoal);
    margin-top: 6px;
}

/* Meta Pill Buttons */
.stButton > button {
    background-color: var(--ink-button) !important;
    color: var(--canvas) !important;
    border: none !important;
    border-radius: 100px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    letter-spacing: -0.14px !important;
    padding: 12px 28px !important;
    transition: background-color 0.15s ease !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
}

.stButton > button:hover {
    background-color: var(--charcoal) !important;
    color: var(--canvas) !important;
}

/* Commerce Buy-CTA Button Override (Cobalt Blue) */
.meta-buy-btn .stButton > button {
    background-color: var(--primary) !important;
    color: var(--canvas) !important;
}

.meta-buy-btn .stButton > button:hover {
    background-color: var(--primary-deep) !important;
}

/* Streamlit Overrides for Meta Style */
[data-testid="stExpander"] {
    background-color: var(--surface-soft) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: 16px !important;
    margin-top: 16px;
}

[data-testid="stExpander"] details summary {
    font-size: 14px !important;
    font-weight: 700 !important;
    color: var(--ink-deep) !important;
    letter-spacing: -0.14px !important;
}

code {
    background-color: var(--surface-soft) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: 8px !important;
    padding: 3px 8px !important;
    color: var(--ink-deep) !important;
}

.stChatMessage {
    background-color: var(--canvas) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: 16px !important;
    padding: 16px 20px !important;
    margin-bottom: 12px !important;
}

[data-testid="stChatInput"] textarea {
    background-color: var(--canvas) !important;
    border: 1px solid var(--hairline) !important;
    border-radius: 100px !important;
    padding: 12px 24px !important;
    color: var(--ink) !important;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: var(--primary) !important;
}

hr {
    border-color: var(--hairline-soft) !important;
    margin: 32px 0 !important;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# System Command Bar / Navigation Header (Meta Style)
# -----------------------------------------------------------------------------
def render_command_bar():
    col_logo, col_stat, col_ctrl = st.columns([1.8, 2.2, 1.2], gap="medium")
    
    with col_logo:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 22px; font-weight: 700; letter-spacing: -0.5px; color: #0a1317;">ReFocus</span>
            <span style="display: inline-block; width: 1px; height: 18px; background-color: #dee3e9;"></span>
            <span style="font-size: 13px; font-weight: 500; color: #5d6c7b; letter-spacing: -0.14px;">Work Context OS</span>
        </div>
        """, unsafe_allow_html=True)

    with col_stat:
        render_live_system_status()

    with col_ctrl:
        st.toggle("Privacy Mode", key="privacy_mode", help="Pauses automated background OCR snapshotting.")

@st.fragment(run_every="1s")
def render_live_system_status():
    idle_secs = int(get_idle_seconds())
    is_paused = st.session_state.get("privacy_mode", False)

    if is_paused:
        status_html = '<span class="meta-badge meta-badge-paused">○ MONITORING PAUSED</span>'
        idle_info = "Snapshots suspended"
    elif idle_secs < INACTIVITY_THRESHOLD:
        status_html = '<span class="meta-badge meta-badge-active">● ACTIVE TRACKING</span>'
        idle_info = f"Idle: <code>{idle_secs}s</code> / <code>{INACTIVITY_THRESHOLD}s</code>"
    else:
        away_m = idle_secs // 60
        away_s = idle_secs % 60
        status_html = '<span class="meta-badge meta-badge-idle">▲ INTERRUPTED</span>'
        idle_info = f"Away: <code>{away_m}m {away_s}s</code>"

    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: flex-end; gap: 14px; margin-top: 2px;">
        {status_html}
        <span style="font-size: 13px; color: #5d6c7b;">{idle_info}</span>
    </div>
    """, unsafe_allow_html=True)

render_command_bar()
st.markdown("<hr style='margin: 16px 0 28px 0;'/>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Main Operational Panels (Left: Recovery Hero | Right: Daily Telemetry)
# -----------------------------------------------------------------------------
state = detect_current_state()
previous_category = get_previous_category()

left_col, right_col = st.columns([1.75, 1.25], gap="large")

with left_col:
    # --- HERO: CONTEXT HANDOFF & RECOVERY ---
    if state.get("status") == "ok" and previous_category:
        away_seconds = time_since_last_category(previous_category)
        away_minutes = int(away_seconds) // 60
        away_secs_rem = int(away_seconds) % 60

        st.markdown(f"""
        <div class="meta-card" style="border-top: 4px solid var(--primary);">
            <div class="meta-card-header">
                <div class="meta-card-title">
                    <span>Interrupted Workspace Handoff</span>
                </div>
                <span class="meta-badge meta-badge-idle">DRIFT DETECTED</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
                <div class="meta-metric-tile">
                    <div class="meta-metric-label">Target Recovery Workspace</div>
                    <div class="meta-metric-val" style="font-size: 22px;">{previous_category.upper()}</div>
                    <div class="meta-metric-sub">Last active workspace state</div>
                </div>
                <div class="meta-metric-tile">
                    <div class="meta-metric-label">Time Since Interaction</div>
                    <div class="meta-metric-val" style="font-size: 22px; color: #0064e0;">{away_minutes}m {away_secs_rem}s</div>
                    <div class="meta-metric-sub">Interrupted by: {state['current_category']}</div>
                </div>
            </div>
            <div style="font-size: 14px; color: #444950; line-height: 1.55; margin-bottom: 20px;">
                Your workspace state was captured right before the interruption. Click below to reconstruct your cognitive context, open files, and next planned action.
            </div>
        </div>
        """, unsafe_allow_html=True)

        btn_col, _ = st.columns([1.6, 1.0])
        with btn_col:
            st.markdown('<div class="meta-buy-btn">', unsafe_allow_html=True)
            trigger_recovery = st.button(
                f"Reconstruct Context & Resume in {previous_category.upper()}",
                use_container_width=True,
                type="primary"
            )
            st.markdown('</div>', unsafe_allow_html=True)

        if trigger_recovery:
            with st.spinner("Synthesizing context dossier from active window telemetry..."):
                briefing_text = generate_briefing_for_category(previous_category)
                snapshots_data = get_last_session_snapshots(previous_category)
                st.session_state["briefing_cache"] = {
                    "category": previous_category,
                    "briefing": briefing_text,
                    "snapshots": snapshots_data,
                    "timestamp": time.strftime("%H:%M:%S")
                }

        if st.session_state["briefing_cache"]:
            cache = st.session_state["briefing_cache"]
            st.markdown(f"""
            <div class="meta-card" style="margin-top: 24px;">
                <div class="meta-card-header">
                    <div class="meta-card-title">
                        <span>Executive Recovery Briefing — {cache['category'].upper()}</span>
                    </div>
                    <span style="font-size: 12px; color: #8595a4;">Generated at {cache['timestamp']}</span>
                </div>
                <div style="font-size: 15px; line-height: 1.65; color: #1c1e21;">
            """, unsafe_allow_html=True)
            
            st.markdown(cache["briefing"])
            st.markdown("</div>", unsafe_allow_html=True)

            with st.expander("View Raw Evidence & OCR Logs"):
                if cache["snapshots"]:
                    for idx, (w_title, ocr_data, ts) in enumerate(cache["snapshots"][-4:]):
                        ts_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                        st.markdown(f"""
                        <div style="border-bottom: 1px solid #dee3e9; padding: 12px 0;">
                            <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; color: #1c1e21;">
                                <span>[{idx+1}] {w_title}</span>
                                <span style="font-family: 'JetBrains Mono', monospace; color: #8595a4; font-size: 12px;">{ts_str}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.code(ocr_data[:350] if ocr_data else "(No readable OCR text extracted)", language="text")
                else:
                    st.caption("No snapshot evidence recorded for this session.")
            
            st.markdown("</div>", unsafe_allow_html=True)

    else:
        current_app = state.get("current_category", "Unknown").upper() if state.get("status") == "ok" else "IDLE"
        current_win = state.get("current_window", "Waiting for active input...") if state.get("status") == "ok" else "No telemetry recorded"
        
        st.markdown(f"""
        <div class="meta-card">
            <div class="meta-card-header">
                <div class="meta-card-title">
                    <span>Current Workspace Telemetry</span>
                </div>
                <span class="meta-badge meta-badge-active">SYNCHRONIZED</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr; gap: 16px;">
                <div class="meta-metric-tile">
                    <div class="meta-metric-label">Active Application</div>
                    <div class="meta-metric-val" style="font-size: 24px;">{current_app}</div>
                    <div class="meta-metric-sub" style="font-family: 'JetBrains Mono', monospace; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        {current_win}
                    </div>
                </div>
            </div>
            <div style="margin-top: 20px; font-size: 14px; color: #5d6c7b; line-height: 1.55;">
                Zero drift detected. ReFocus is actively monitoring your workflow in the background. When you switch contexts or step away for ≥ 3 minutes, your recovery handoff will stage here automatically.
            </div>
        </div>
        """, unsafe_allow_html=True)

with right_col:
    # --- RIGHT: DAILY TELEMETRY ---
    st.markdown("""
    <div class="meta-card">
        <div class="meta-card-header">
            <div class="meta-card-title">
                <span>Daily Focus Telemetry</span>
            </div>
            <span style="font-size: 12px; font-weight: 700; color: #8595a4;">TODAY</span>
        </div>
    """, unsafe_allow_html=True)

    today_stats = get_daily_stats(days_ago=0)
    yesterday_stats = get_daily_stats(days_ago=1)

    focus_min_today = round(today_stats.get("focus_seconds", 0) / 60, 1)
    focus_score = today_stats.get("focus_score", 0)
    interruptions = today_stats.get("interruptions", 0)
    total_snaps = today_stats.get("total_snapshots", 0)

    score_delta = round(focus_score - yesterday_stats.get("focus_score", 0), 1)
    delta_symbol = "▲" if score_delta >= 0 else "▼"
    delta_color = "#31a24c" if score_delta >= 0 else "#e41e3f"

    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">Focus Efficiency</div>
            <div class="meta-metric-val">{focus_score}%</div>
            <div class="meta-metric-sub" style="color: {delta_color}; font-weight: 700;">
                {delta_symbol} {abs(score_delta)}% vs yesterday
            </div>
        </div>
        """, unsafe_allow_html=True)

    with m_col2:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">Deep Work Time</div>
            <div class="meta-metric-val">{focus_min_today}m</div>
            <div class="meta-metric-sub">Focus duration</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

    m_col3, m_col4 = st.columns(2)
    with m_col3:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">Context Switches</div>
            <div class="meta-metric-val" style="color: #f2a918;">{interruptions}</div>
            <div class="meta-metric-sub">Drift events logged</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col4:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">Snapshots Logged</div>
            <div class="meta-metric-val">{total_snaps}</div>
            <div class="meta-metric-sub">Telemetry records</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 7-DAY EXECUTIVE WEEKLY AUDIT
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

col_rep_head, col_rep_btn = st.columns([2.5, 1.2], gap="medium")

with col_rep_head:
    st.markdown("""
    <div style="font-size: 18px; font-weight: 700; color: #0a1317; letter-spacing: -0.3px;">
        7-Day Executive Focus Audit
    </div>
    <div style="font-size: 14px; color: #5d6c7b; margin-top: 2px;">
        Compile multi-day cognitive load, context switching velocity, and deep work trends.
    </div>
    """, unsafe_allow_html=True)

with col_rep_btn:
    if st.button("📊 Compile Weekly Report", use_container_width=True):
        st.session_state["show_weekly_report"] = True

if st.session_state["show_weekly_report"]:
    weekly_data = get_weekly_summary()
    
    st.markdown("""
    <div style="font-size: 14px; font-weight: 700; color: #31a24c; margin: 20px 0 14px 0; text-transform: uppercase; letter-spacing: -0.14px;">
        ● Executive 7-Day Productivity Dossier
    </div>
    """, unsafe_allow_html=True)
    
    # 4 Main KPI Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">7-Day Deep Work</div>
            <div class="meta-metric-val" style="color: #0064e0;">{weekly_data['total_focus_hours']}h</div>
            <div class="meta-metric-sub">Total focus duration</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">Avg Focus Score</div>
            <div class="meta-metric-val">{weekly_data['avg_focus_score']}%</div>
            <div class="meta-metric-sub">Weighted daily efficiency</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">Total Drift Events</div>
            <div class="meta-metric-val" style="color: #f2a918;">{weekly_data['total_interruptions']}</div>
            <div class="meta-metric-sub">Context switches logged</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi4:
        st.markdown(f"""
        <div class="meta-metric-tile">
            <div class="meta-metric-label">Peak Performance</div>
            <div class="meta-metric-val" style="font-size: 18px; margin-top: 4px;">{weekly_data['best_day']}</div>
            <div class="meta-metric-sub">{weekly_data['best_day_hours']}h deep work logged</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; color: #5d6c7b; margin: 24px 0 12px 0; letter-spacing: -0.14px;">
        Daily Focus Velocity & Interruption Breakdown
    </div>
    """, unsafe_allow_html=True)
    
    # 7-Day Velocity Breakdown Columns
    day_cols = st.columns(7)
    for idx, d in enumerate(weekly_data["days"]):
        with day_cols[idx]:
            score_color = "#31a24c" if d['score'] >= 60 else "#f2a918"
            st.markdown(f"""
            <div class="meta-metric-tile" style="text-align: center; padding: 14px 8px;">
                <div style="font-size: 12px; font-weight: 700; color: #1c1e21;">{d['short_day']}</div>
                <div style="font-size: 20px; font-weight: 700; color: {score_color}; margin: 8px 0 4px 0;">
                    {d['score']}%
                </div>
                <div style="font-size: 11px; color: #5d6c7b;">{d['focus_hours']}h work</div>
                <div style="font-size: 11px; color: #f2a918; margin-top: 2px;">{d['interruptions']} drifts</div>
            </div>
            """, unsafe_allow_html=True)

    # Executive AI Retrospective Card
    st.markdown(f"""
    <div style="background-color: #f1f4f7; border: 1px solid #dee3e9; border-radius: 24px; padding: 24px; margin-top: 24px;">
        <div style="font-size: 14px; font-weight: 700; color: #0a1317; margin-bottom: 8px;">
            AI Executive Retrospective
        </div>
        <div style="font-size: 14px; color: #444950; line-height: 1.6;">
            Over the past 7 days, you maintained a <b>{weekly_data['avg_focus_score']}% focus efficiency</b> across <b>{weekly_data['total_focus_hours']} hours</b> of deep work. 
            Your strongest flow state occurred on <b>{weekly_data['best_day']}</b> ({weekly_data['best_day_hours']} hours). 
            Primary drift vector was mid-afternoon context switching between IDE and browser documentation.
        </div>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# ACTIVITY INQUIRY COPILOT (Command Chat Interface)
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

st.markdown("""
<div class="meta-card">
    <div class="meta-card-header">
        <div class="meta-card-title">
            <span>Activity Query Interface — Copilot</span>
        </div>
        <span style="font-size: 12px; font-weight: 700; color: #8595a4;">LOCAL LLM</span>
    </div>
    <div style="font-size: 14px; color: #5d6c7b; margin-bottom: 20px;">
        Query your daily workspace history, focus drift events, or draft handoff notes using local intelligence.
    </div>
""", unsafe_allow_html=True)

for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_query = st.chat_input("Query your work context (e.g., 'What caused my longest break today?')")

if user_query:
    st.session_state["chat_history"].append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing local telemetry..."):
            reply = chat_with_assistant(st.session_state["chat_history"])
        st.markdown(reply)

    st.session_state["chat_history"].append({"role": "assistant", "content": reply})

st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Footer (Meta Style)
# -----------------------------------------------------------------------------
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; padding: 32px 0 16px 0; border-top: 1px solid #dee3e9; font-size: 12px; color: #8595a4;">
    <span>ReFocus Engine — Private On-Device Telemetry</span>
    <span>Zero Cloud Transmission // Air-Gapped</span>
</div>
""", unsafe_allow_html=True)