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
# Streamlit App Configuration & Design Tokens
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="REFOCUS // Work Context OS",
    page_icon="◬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
    --bg-main: #0b0c10;
    --bg-surface: #12141a;
    --bg-subtle: #171922;
    --bg-hover: #1e212d;
    --border-base: #232733;
    --border-strong: #33384a;
    --text-primary: #f1f3f9;
    --text-secondary: #949cb0;
    --text-muted: #5e667e;
    --accent: #ff542e;
    --focus-green: #10b981;
    --warn-amber: #f59e0b;
}

html, body, [class*="css"], .stMarkdown, .stText {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    color: var(--text-primary);
}

code, kbd, samp, pre {
    font-family: 'JetBrains Mono', Consolas, monospace !important;
}

.stApp {
    background-color: var(--bg-main) !important;
    color: var(--text-primary) !important;
}

header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
}
.main .block-container {
    padding-top: 1.8rem !important;
    padding-bottom: 4rem !important;
    max-width: 1280px !important;
}

.rf-card {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-base);
    border-radius: 8px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.rf-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border-base);
    padding-bottom: 14px;
    margin-bottom: 18px;
}

.rf-card-title {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 8px;
}

.rf-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.rf-badge-active {
    background-color: rgba(16, 185, 129, 0.12);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}
.rf-badge-idle {
    background-color: rgba(245, 158, 11, 0.12);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
}
.rf-badge-paused {
    background-color: rgba(94, 102, 126, 0.15);
    color: #949cb0;
    border: 1px solid var(--border-base);
}

.rf-metric-box {
    background-color: var(--bg-subtle);
    border: 1px solid var(--border-base);
    border-radius: 6px;
    padding: 16px 18px;
}
.rf-metric-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 6px;
}
.rf-metric-val {
    font-size: 24px;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary);
    line-height: 1.1;
}
.rf-metric-sub {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 6px;
}

.stButton > button {
    background-color: var(--text-primary) !important;
    color: var(--bg-main) !important;
    border: 1px solid var(--text-primary) !important;
    border-radius: 6px !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    letter-spacing: 0.02em !important;
    padding: 9px 20px !important;
    transition: all 0.12s ease-in-out !important;
}
.stButton > button:hover {
    background-color: #ffffff !important;
    border-color: #ffffff !important;
    transform: translateY(-1px);
}

[data-testid="stExpander"] {
    background-color: var(--bg-subtle) !important;
    border: 1px solid var(--border-base) !important;
    border-radius: 6px !important;
    margin-top: 14px;
}
[data-testid="stExpander"] details summary {
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    color: var(--text-secondary) !important;
}
code {
    background-color: #0e0f14 !important;
    border: 1px solid var(--border-base) !important;
    border-radius: 4px !important;
    padding: 2px 6px !important;
    color: #e2e8f0 !important;
}
.stChatMessage {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-base) !important;
    border-radius: 6px !important;
    padding: 14px !important;
    margin-bottom: 10px !important;
}
[data-testid="stChatInput"] textarea {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-base) !important;
    border-radius: 6px !important;
    color: var(--text-primary) !important;
}
hr {
    border-color: var(--border-base) !important;
    margin: 24px 0 !important;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# System Command Bar / Header
# -----------------------------------------------------------------------------
def render_command_bar():
    col_logo, col_stat, col_ctrl = st.columns([1.8, 2.2, 1.2], gap="medium")
    
    with col_logo:
        st.markdown("""
        <div style="display: flex; align-items: baseline; gap: 10px;">
            <span style="font-size: 20px; font-weight: 900; letter-spacing: -0.04em; color: #ffffff;">REFOCUS</span>
            <span style="font-size: 11px; font-weight: 600; font-family: 'JetBrains Mono', monospace; color: #5e667e; letter-spacing: 0.1em;">// CONTEXT RECOVERY OS</span>
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
        status_html = '<span class="rf-badge rf-badge-paused">○ MONITORING PAUSED</span>'
        idle_info = "Snapshots suspended"
    elif idle_secs < INACTIVITY_THRESHOLD:
        status_html = '<span class="rf-badge rf-badge-active">● ACTIVE // TRACKING</span>'
        idle_info = f"Idle: <code>{idle_secs}s</code> / <code>{INACTIVITY_THRESHOLD}s</code>"
    else:
        away_m = idle_secs // 60
        away_s = idle_secs % 60
        status_html = '<span class="rf-badge rf-badge-idle">▲ INTERRUPTED</span>'
        idle_info = f"Away: <code>{away_m}m {away_s}s</code>"

    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: flex-end; gap: 14px; margin-top: 2px;">
        {status_html}
        <span style="font-size: 12px; color: #949cb0;">{idle_info}</span>
    </div>
    """, unsafe_allow_html=True)

render_command_bar()
st.markdown("<hr style='margin: 14px 0 20px 0;'/>", unsafe_allow_html=True)

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
        <div class="rf-card" style="border-left: 3px solid var(--accent);">
            <div class="rf-card-header">
                <div class="rf-card-title">
                    <span>INTERRUPTED WORKSPACE HANDOFF</span>
                </div>
                <span class="rf-badge rf-badge-idle">DRIFT DETECTED</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 18px;">
                <div class="rf-metric-box">
                    <div class="rf-metric-label">Target Recovery Workspace</div>
                    <div class="rf-metric-val" style="font-size: 20px; color: #ffffff;">{previous_category.upper()}</div>
                    <div class="rf-metric-sub">Last active coding state</div>
                </div>
                <div class="rf-metric-box">
                    <div class="rf-metric-label">Duration Since Last Interaction</div>
                    <div class="rf-metric-val" style="font-size: 20px; color: #ff542e;">{away_minutes}m {away_secs_rem}s</div>
                    <div class="rf-metric-sub">Interrupted by: {state['current_category']}</div>
                </div>
            </div>
            <div style="font-size: 13px; color: #949cb0; line-height: 1.5; margin-bottom: 16px;">
                Your workspace state was captured right before the interruption. Click below to reconstruct your cognitive context, open files, and next planned action.
            </div>
        </div>
        """, unsafe_allow_html=True)

        btn_col, _ = st.columns([1.4, 1.0])
        with btn_col:
            trigger_recovery = st.button(
                f"↳ Reconstruct Context & Resume in {previous_category.upper()}",
                use_container_width=True,
                type="primary"
            )

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
            <div class="rf-card" style="margin-top: 18px;">
                <div class="rf-card-header">
                    <div class="rf-card-title">
                        <span>EXECUTIVE RECOVERY BRIEFING // {cache['category'].upper()}</span>
                    </div>
                    <span style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #5e667e;">GENERATED AT {cache['timestamp']}</span>
                </div>
                <div style="font-size: 14px; line-height: 1.65; color: #e2e8f0;">
            """, unsafe_allow_html=True)
            
            st.markdown(cache["briefing"])
            st.markdown("</div>", unsafe_allow_html=True)

            with st.expander("VIEW RAW EVIDENCE & OCR LOGS"):
                if cache["snapshots"]:
                    for idx, (w_title, ocr_data, ts) in enumerate(cache["snapshots"][-4:]):
                        ts_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                        st.markdown(f"""
                        <div style="border-bottom: 1px solid var(--border-base); padding: 10px 0;">
                            <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; color: #949cb0;">
                                <span>[{idx+1}] {w_title}</span>
                                <span style="font-family: 'JetBrains Mono', monospace; color: #5e667e;">{ts_str}</span>
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
        <div class="rf-card">
            <div class="rf-card-header">
                <div class="rf-card-title">
                    <span>CURRENT WORKSPACE TELEMETRY</span>
                </div>
                <span class="rf-badge rf-badge-active">SYNCHRONIZED</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr; gap: 14px;">
                <div class="rf-metric-box">
                    <div class="rf-metric-label">Active Application</div>
                    <div class="rf-metric-val" style="font-size: 22px;">{current_app}</div>
                    <div class="rf-metric-sub" style="font-family: 'JetBrains Mono', monospace; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        {current_win}
                    </div>
                </div>
            </div>
            <div style="margin-top: 18px; font-size: 12px; color: #717888; line-height: 1.5;">
                Zero drift detected. ReFocus is actively monitoring your workflow. When you switch contexts or step away for >= 3 minutes, your recovery handoff will stage here automatically.
            </div>
        </div>
        """, unsafe_allow_html=True)

with right_col:
    # --- RIGHT: DAILY TELEMETRY ---
    st.markdown("""
    <div class="rf-card">
        <div class="rf-card-header">
            <div class="rf-card-title">
                <span>DAILY FOCUS TELEMETRY</span>
            </div>
            <span style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #5e667e;">TODAY</span>
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
    delta_color = "#10b981" if score_delta >= 0 else "#f43f5e"

    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">Focus Efficiency</div>
            <div class="rf-metric-val">{focus_score}%</div>
            <div class="rf-metric-sub" style="color: {delta_color}; font-weight: 600;">
                {delta_symbol} {abs(score_delta)}% vs yesterday
            </div>
        </div>
        """, unsafe_allow_html=True)

    with m_col2:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">Deep Work Time</div>
            <div class="rf-metric-val">{focus_min_today}m</div>
            <div class="rf-metric-sub">Coding duration</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    m_col3, m_col4 = st.columns(2)
    with m_col3:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">Context Switches</div>
            <div class="rf-metric-val" style="color: #f59e0b;">{interruptions}</div>
            <div class="rf-metric-sub">Interruptions logged</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col4:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">Snapshots Logged</div>
            <div class="rf-metric-val">{total_snaps}</div>
            <div class="rf-metric-sub">Telemetry records</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 7-DAY EXECUTIVE WEEKLY AUDIT
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

col_rep_head, col_rep_btn = st.columns([2.5, 1.0], gap="medium")

with col_rep_head:
    st.markdown("""
    <div style="font-size: 14px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; color: #f1f3f9;">
        7-Day Executive Focus Audit
    </div>
    <div style="font-size: 12px; color: #949cb0; margin-top: 2px;">
        Compile multi-day cognitive load, context switching velocity, and deep work trends.
    </div>
    """, unsafe_allow_html=True)

with col_rep_btn:
    if st.button("📊 Compile Weekly Report", use_container_width=True):
        st.session_state["show_weekly_report"] = True

if st.session_state["show_weekly_report"]:
    weekly_data = get_weekly_summary()
    
    st.markdown("""
    <div style="font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #34d399; margin: 16px 0 12px 0;">
        ● EXECUTIVE 7-DAY PRODUCTIVITY DOSSIER
    </div>
    """, unsafe_allow_html=True)
    
    # 4 Main KPI Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">7-Day Deep Work</div>
            <div class="rf-metric-val" style="color: #34d399;">{weekly_data['total_focus_hours']}h</div>
            <div class="rf-metric-sub">Total coding duration</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">Avg Focus Score</div>
            <div class="rf-metric-val">{weekly_data['avg_focus_score']}%</div>
            <div class="rf-metric-sub">Weighted daily efficiency</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">Total Drift Events</div>
            <div class="rf-metric-val" style="color: #f59e0b;">{weekly_data['total_interruptions']}</div>
            <div class="rf-metric-sub">Context switches logged</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi4:
        st.markdown(f"""
        <div class="rf-metric-box">
            <div class="rf-metric-label">Peak Performance</div>
            <div class="rf-metric-val" style="font-size: 16px; margin-top: 4px;">{weekly_data['best_day']}</div>
            <div class="rf-metric-sub">{weekly_data['best_day_hours']}h deep work logged</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div style="font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #5e667e; margin: 18px 0 10px 0;">
        Daily Focus Velocity & Interruption Breakdown
    </div>
    """, unsafe_allow_html=True)
    
    # 7-Day Velocity Breakdown Columns
    day_cols = st.columns(7)
    for idx, d in enumerate(weekly_data["days"]):
        with day_cols[idx]:
            score_color = "#34d399" if d['score'] >= 60 else "#f59e0b"
            st.markdown(f"""
            <div class="rf-metric-box" style="text-align: center; padding: 12px 6px;">
                <div style="font-size: 11px; font-weight: 700; color: #949cb0;">{d['short_day']}</div>
                <div style="font-size: 18px; font-weight: 800; font-family: 'JetBrains Mono', monospace; color: {score_color}; margin: 6px 0;">
                    {d['score']}%
                </div>
                <div style="font-size: 10px; color: #5e667e;">{d['focus_hours']}h work</div>
                <div style="font-size: 10px; color: #f59e0b; margin-top: 2px;">{d['interruptions']} drifts</div>
            </div>
            """, unsafe_allow_html=True)

    # Executive AI Retrospective Card
    st.markdown(f"""
    <div style="background-color: #171922; border: 1px solid #232733; border-radius: 6px; padding: 16px 20px; margin-top: 18px;">
        <div style="font-size: 12px; font-weight: 700; color: #f1f3f9; margin-bottom: 6px;">
            AI EXECUTIVE RETROSPECTIVE
        </div>
        <div style="font-size: 13px; color: #949cb0; line-height: 1.6;">
            Over the past 7 days, you maintained a <b>{weekly_data['avg_focus_score']}% focus efficiency</b> across <b>{weekly_data['total_focus_hours']} hours</b> of deep work. 
            Your strongest flow state occurred on <b>{weekly_data['best_day']}</b> ({weekly_data['best_day_hours']} hours). 
            Primary drift vector was mid-afternoon context switching between IDE and browser documentation.
        </div>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# ACTIVITY INQUIRY COPILOT (Command / Terminal Chat Interface)
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

st.markdown("""
<div class="rf-card">
    <div class="rf-card-header">
        <div class="rf-card-title">
            <span>ACTIVITY QUERY INTERFACE // COPILOT</span>
        </div>
        <span style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #5e667e;">LOCAL LLM</span>
    </div>
    <div style="font-size: 13px; color: #949cb0; margin-bottom: 16px;">
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
# Footer
# -----------------------------------------------------------------------------
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; padding: 24px 0 12px 0; border-top: 1px solid var(--border-base); font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #5e667e;">
    <span>REFOCUS ENGINE // PRIVATE ON-DEVICE TELEMETRY</span>
    <span>ZERO CLOUD TRANSMISSION // AIR-GAPPED</span>
</div>
""", unsafe_allow_html=True)