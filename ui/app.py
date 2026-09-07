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
# Streamlit App Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ReFocus — Work Context OS",
    page_icon="◬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------------------------------------------------------------
# META-INSPIRED DESIGN SYSTEM
# White canvas, pill geometry, cobalt action color, hairline borders,
# 16–32px card radii, 100px button radii, flat elevation.
# -----------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    /* Meta tokens */
    --canvas: #ffffff;
    --surface-soft: #f1f4f7;
    --ink-deep: #0a1317;
    --ink: #1c1e21;
    --charcoal: #444950;
    --steel: #5d6c7b;
    --stone: #8595a4;
    --hairline: #ced0d4;
    --hairline-soft: #dee3e9;
    --primary: #0064e0;
    --primary-deep: #0457cb;
    --primary-soft: #0091ff;
    --success: #31a24c;
    --attention: #f2a918;
    --warning: #f7b928;
    --critical: #e41e3f;
    /* Radii */
    --r-lg: 8px;
    --r-xl: 16px;
    --r-xxl: 24px;
    --r-xxxl: 32px;
    --r-full: 100px;
}

html, body, [class*="css"], .stMarkdown, .stText, p, span, div {
    font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
    color: var(--ink);
}

h1, h2, h3, .rf-display {
    font-family: 'Montserrat', 'Helvetica Neue', Arial, sans-serif;
}

code, kbd, samp, pre, .rf-mono {
    font-family: 'JetBrains Mono', Consolas, monospace !important;
}

.stApp {
    background-color: var(--canvas) !important;
    color: var(--ink) !important;
}

header[data-testid="stHeader"] {
    background: rgba(255, 255, 255, 0.92) !important;
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--hairline-soft) !important;
}

.main .block-container {
    padding-top: 0rem !important;
    padding-bottom: 4rem !important;
    max-width: 1280px !important;
}

/* ---------- Promo banner (above nav, like meta.com) ---------- */
.rf-promo {
    background-color: var(--ink-deep);
    color: #ffffff;
    border-radius: var(--r-full);
    padding: 10px 24px;
    margin: 14px 0 18px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: -0.14px;
}
.rf-promo .rf-mono { color: #9fb6cf; font-size: 12px; }

/* ---------- Cards ---------- */
.rf-card {
    background-color: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--r-xxxl);
    padding: 32px;
    margin-bottom: 24px;
}
.rf-card-soft {
    background-color: var(--surface-soft);
    border: none;
    border-radius: var(--r-xxl);
    padding: 28px;
}
.rf-card-dark {
    background-color: var(--ink-deep);
    color: #ffffff;
    border: none;
    border-radius: var(--r-xxxl);
    padding: 40px;
    margin-bottom: 24px;
}
.rf-card-dark .rf-title, .rf-card-dark p { color: #ffffff; }

.rf-eyebrow {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: var(--steel);
    margin-bottom: 8px;
}
.rf-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 24px;
    font-weight: 500;
    line-height: 1.25;
    color: var(--ink-deep);
    margin-bottom: 4px;
}
.rf-title-lg {
    font-family: 'Montserrat', sans-serif;
    font-size: 36px;
    font-weight: 500;
    line-height: 1.28;
    color: var(--ink-deep);
    letter-spacing: -0.5px;
}
.rf-sub {
    font-size: 16px;
    line-height: 1.5;
    letter-spacing: -0.16px;
    color: var(--charcoal);
}

/* ---------- Badges (pill) ---------- */
.rf-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: var(--r-full);
    font-size: 12px;
    font-weight: 700;
    line-height: 1.33;
}
.rf-badge-success { background: var(--success); color: #fff; }
.rf-badge-attention { background: var(--attention); color: #fff; }
.rf-badge-warning { background: var(--warning); color: var(--ink-deep); }
.rf-badge-critical { background: var(--critical); color: #fff; }
.rf-badge-neutral {
    background: var(--surface-soft);
    color: var(--steel);
    border: 1px solid var(--hairline-soft);
}
.rf-badge-cobalt { background: var(--primary); color: #fff; }

/* ---------- Metric tiles ---------- */
.rf-metric {
    background-color: var(--surface-soft);
    border-radius: var(--r-xl);
    padding: 20px 22px;
    height: 100%;
}
.rf-metric-bordered {
    background-color: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--r-xl);
    padding: 20px 22px;
    height: 100%;
}
.rf-metric-label {
    font-size: 12px;
    font-weight: 700;
    line-height: 1.33;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--steel);
    margin-bottom: 6px;
}
.rf-metric-val {
    font-family: 'Montserrat', sans-serif;
    font-size: 28px;
    font-weight: 700;
    line-height: 1.17;
    color: var(--ink-deep);
}
.rf-metric-sub {
    font-size: 14px;
    line-height: 1.43;
    color: var(--steel);
    margin-top: 4px;
}

/* ---------- Buttons: always pill ---------- */
.stButton > button {
    border-radius: var(--r-full) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    letter-spacing: -0.14px !important;
    padding: 12px 28px !important;
    height: 44px !important;
    transition: all 0.15s ease-out !important;
}
/* Primary (default) = black pill (marketing CTA) */
.stButton > button[kind="primary"],
.stButton > button {
    background-color: var(--ink-deep) !important;
    color: #ffffff !important;
    border: none !important;
}
.stButton > button:hover {
    background-color: var(--charcoal) !important;
    transform: translateY(-1px);
}
/* Secondary = outlined ghost */
.stButton > button[kind="secondary"] {
    background-color: transparent !important;
    color: var(--ink-deep) !important;
    border: 2px solid var(--ink-deep) !important;
}
.stButton > button[kind="secondary"]:hover {
    background-color: var(--surface-soft) !important;
}

/* ---------- Toggle ---------- */
[data-testid="stToggle"] label { font-size: 14px; font-weight: 600; }

/* ---------- Expander ---------- */
[data-testid="stExpander"] {
    background-color: var(--canvas) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: var(--r-xl) !important;
    margin-top: 16px;
}
[data-testid="stExpander"] details summary {
    font-size: 14px !important;
    font-weight: 700 !important;
    color: var(--ink) !important;
}

/* ---------- Code ---------- */
code {
    background-color: var(--surface-soft) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: 6px !important;
    padding: 2px 6px !important;
    color: var(--ink-deep) !important;
}

/* ---------- Chat ---------- */
.stChatMessage {
    background-color: var(--surface-soft) !important;
    border: none !important;
    border-radius: var(--r-xl) !important;
    padding: 16px !important;
    margin-bottom: 12px !important;
}
[data-testid="stChatInput"] textarea {
    background-color: var(--surface-soft) !important;
    border: 1px solid var(--hairline) !important;
    border-radius: var(--r-full) !important;
    color: var(--ink) !important;
    padding-left: 20px !important;
}
[data-testid="stChatInput"] textarea:focus {
    border: 2px solid var(--primary) !important;
}

hr { border-color: var(--hairline-soft) !important; margin: 32px 0 !important; }

/* ---------- Live status dot animation ---------- */
@keyframes rf-pulse {
    0% { box-shadow: 0 0 0 0 rgba(49, 162, 76, 0.45); }
    70% { box-shadow: 0 0 0 8px rgba(49, 162, 76, 0); }
    100% { box-shadow: 0 0 0 0 rgba(49, 162, 76, 0); }
}
.rf-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--success);
    animation: rf-pulse 2s infinite;
    margin-right: 6px;
}
.rf-dot-amber { background: var(--attention); animation: none; }
.rf-dot-gray { background: var(--stone); animation: none; }

/* ---------- Wordmark ---------- */
.rf-wordmark {
    font-family: 'Montserrat', sans-serif;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: var(--ink-deep);
}
.rf-wordmark span { color: var(--primary); }

/* ---------- Day tile (weekly) ---------- */
.rf-day {
    background-color: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--r-xl);
    padding: 14px 8px;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Promo banner + nav command bar
# -----------------------------------------------------------------------------
def render_command_bar():
    st.markdown("""
    <div class="rf-promo">
        <span>ON-DEVICE TELEMETRY &nbsp;·&nbsp; ZERO CLOUD TRANSMISSION &nbsp;·&nbsp; LOCAL LLM INTELLIGENCE</span>
        <span class="rf-mono">v2.0 // META EDITION</span>
    </div>
    """, unsafe_allow_html=True)

    col_logo, col_stat, col_ctrl = st.columns([1.6, 2.4, 1.0], gap="medium")

    with col_logo:
        st.markdown(
            '<div class="rf-wordmark">ReFocus<span>.</span></div>'
            '<div style="font-size:12px;font-weight:600;color:var(--steel);letter-spacing:0.06em;text-transform:uppercase;margin-top:2px;">Work Context OS</div>',
            unsafe_allow_html=True,
        )

    with col_stat:
        render_live_system_status()

    with col_ctrl:
        st.toggle("Privacy Mode", key="privacy_mode", help="Pauses automated background OCR snapshotting.")

@st.fragment(run_every="1s")
def render_live_system_status():
    idle_secs = int(get_idle_seconds())
    is_paused = st.session_state.get("privacy_mode", False)

    if is_paused:
        badge = '<span class="rf-badge rf-badge-neutral"><span class="rf-dot rf-dot-gray" style="margin-right:0;"></span>MONITORING PAUSED</span>'
        info = "Snapshots suspended"
    elif idle_secs < INACTIVITY_THRESHOLD:
        badge = '<span class="rf-badge rf-badge-success"><span class="rf-dot" style="margin-right:0;"></span>ACTIVE · TRACKING</span>'
        info = f"Idle <code>{idle_secs}s</code> / <code>{INACTIVITY_THRESHOLD}s</code>"
    else:
        away_m = idle_secs // 60
        away_s = idle_secs % 60
        badge = '<span class="rf-badge rf-badge-attention"><span class="rf-dot rf-dot-amber" style="margin-right:0;"></span>INTERRUPTED</span>'
        info = f"Away <code>{away_m}m {away_s}s</code>"

    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:flex-end;gap:14px;margin-top:6px;">
        {badge}
        <span style="font-size:13px;color:var(--steel);">{info}</span>
    </div>
    """, unsafe_allow_html=True)

render_command_bar()
st.markdown("<hr style='margin:18px 0 28px 0;'/>", unsafe_allow_html=True)

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
        <div class="rf-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;">
                <div class="rf-eyebrow" style="margin-bottom:0;">Interrupted Workspace Handoff</div>
                <span class="rf-badge rf-badge-warning">DRIFT DETECTED</span>
            </div>
            <div class="rf-title-lg" style="margin-bottom:8px;">
                Pick up exactly where<br/>you left off.
            </div>
            <div class="rf-sub" style="margin-bottom:24px;">
                Your <b>{previous_category.upper()}</b> workspace state was captured moments before the interruption.
                Reconstruct your files, thread of thought, and next action in one click.
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
                <div class="rf-metric">
                    <div class="rf-metric-label">Recovery Target</div>
                    <div class="rf-metric-val" style="font-size:22px;">{previous_category.upper()}</div>
                    <div class="rf-metric-sub">Last active workspace</div>
                </div>
                <div class="rf-metric">
                    <div class="rf-metric-label">Time Since Drift</div>
                    <div class="rf-metric-val" style="font-size:22px;color:var(--primary);">{away_minutes}m {away_secs_rem}s</div>
                    <div class="rf-metric-sub">Interrupted by: {state['current_category']}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        btn_col, _ = st.columns([1.4, 1.0])
        with btn_col:
            trigger_recovery = st.button(
                f"Reconstruct Context — Resume {previous_category.upper()}",
                use_container_width=True,
                type="primary"
            )

        if trigger_recovery:
            with st.spinner("Synthesizing context dossier from work telemetry..."):
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
            <div class="rf-card" style="margin-top:20px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                    <div class="rf-eyebrow" style="margin-bottom:0;">Executive Recovery Briefing — {cache['category'].upper()}</div>
                    <span class="rf-badge rf-badge-cobalt">GENERATED {cache['timestamp']}</span>
                </div>
            """, unsafe_allow_html=True)

            st.markdown(cache["briefing"])

            with st.expander("View raw evidence & OCR logs"):
                if cache["snapshots"]:
                    for idx, (w_title, ocr_data, ts) in enumerate(cache["snapshots"][-4:]):
                        ts_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                        st.markdown(f"""
                        <div style="border-bottom:1px solid var(--hairline-soft);padding:10px 0;">
                            <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:700;color:var(--charcoal);">
                                <span>[{idx+1}] {w_title}</span>
                                <span class="rf-mono" style="color:var(--stone);font-weight:500;">{ts_str}</span>
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
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;">
                <div class="rf-eyebrow" style="margin-bottom:0;">Current Workspace Telemetry</div>
                <span class="rf-badge rf-badge-success">SYNCHRONIZED</span>
            </div>
            <div class="rf-title-lg" style="margin-bottom:8px;">You're in flow.</div>
            <div class="rf-metric" style="margin-bottom:16px;">
                <div class="rf-metric-label">Active Application</div>
                <div class="rf-metric-val" style="font-size:22px;">{current_app}</div>
                <div class="rf-metric-sub rf-mono" style="font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{current_win}</div>
            </div>
            <div class="rf-sub" style="font-size:14px;">
                Zero drift detected. ReFocus is quietly watching — switch context or step away for 3+ minutes
                and your recovery handoff will stage here automatically.
            </div>
        </div>
        """, unsafe_allow_html=True)

with right_col:
    # --- RIGHT: DAILY TELEMETRY ---
    st.markdown("""
    <div class="rf-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;">
            <div class="rf-eyebrow" style="margin-bottom:0;">Daily Focus Telemetry</div>
            <span class="rf-badge rf-badge-neutral">TODAY</span>
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
    delta_color = "var(--success)" if score_delta >= 0 else "var(--critical)"

    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.markdown(f"""
        <div class="rf-metric-bordered">
            <div class="rf-metric-label">Focus Efficiency</div>
            <div class="rf-metric-val">{focus_score}%</div>
            <div class="rf-metric-sub" style="color:{delta_color};font-weight:700;">{delta_symbol} {abs(score_delta)}% vs yesterday</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col2:
        st.markdown(f"""
        <div class="rf-metric-bordered">
            <div class="rf-metric-label">Deep Work Time</div>
            <div class="rf-metric-val">{focus_min_today}m</div>
            <div class="rf-metric-sub">Focused duration</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    m_col3, m_col4 = st.columns(2)
    with m_col3:
        st.markdown(f"""
        <div class="rf-metric-bordered">
            <div class="rf-metric-label">Context Switches</div>
            <div class="rf-metric-val" style="color:var(--attention);">{interruptions}</div>
            <div class="rf-metric-sub">Interruptions logged</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col4:
        st.markdown(f"""
        <div class="rf-metric-bordered">
            <div class="rf-metric-label">Snapshots</div>
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
    <div class="rf-title">7-Day Focus Audit</div>
    <div class="rf-sub" style="font-size:14px; margin-top:2px;">
        Compile multi-day cognitive load, context-switch velocity, and deep-work trends.
    </div>
    """, unsafe_allow_html=True)

with col_rep_btn:
    if st.button("Compile Weekly Report", use_container_width=True):
        st.session_state["show_weekly_report"] = True

if st.session_state["show_weekly_report"]:
    weekly_data = get_weekly_summary()

    # Dark promo-strip style header card
    st.markdown(f"""
    <div class="rf-card-dark" style="margin-top:20px;">
        <div class="rf-eyebrow" style="color:#9fb6cf;">Executive 7-Day Productivity Dossier</div>
        <div style="font-family:'Montserrat',sans-serif;font-size:32px;font-weight:500;line-height:1.25;margin:6px 0 14px;">
            {weekly_data['total_focus_hours']} hours of deep work.<br/>{weekly_data['avg_focus_score']}% average focus.
        </div>
        <div style="font-size:14px;color:#c9d4e0;line-height:1.6;max-width:720px;">
            Your strongest flow state occurred on <b style="color:#fff;">{weekly_data['best_day']}</b>
            ({weekly_data['best_day_hours']}h deep work), with {weekly_data['total_interruptions']} total drift events
            across the week.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 4 KPI tiles
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(f"""
        <div class="rf-metric">
            <div class="rf-metric-label">7-Day Deep Work</div>
            <div class="rf-metric-val" style="color:var(--success);">{weekly_data['total_focus_hours']}h</div>
            <div class="rf-metric-sub">Total focused duration</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"""
        <div class="rf-metric">
            <div class="rf-metric-label">Avg Focus Score</div>
            <div class="rf-metric-val">{weekly_data['avg_focus_score']}%</div>
            <div class="rf-metric-sub">Weighted daily efficiency</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"""
        <div class="rf-metric">
            <div class="rf-metric-label">Drift Events</div>
            <div class="rf-metric-val" style="color:var(--attention);">{weekly_data['total_interruptions']}</div>
            <div class="rf-metric-sub">Context switches logged</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi4:
        st.markdown(f"""
        <div class="rf-metric">
            <div class="rf-metric-label">Peak Day</div>
            <div class="rf-metric-val" style="font-size:18px;margin-top:6px;">{weekly_data['best_day']}</div>
            <div class="rf-metric-sub">{weekly_data['best_day_hours']}h deep work</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="rf-eyebrow" style="margin:22px 0 12px 0;">Daily focus velocity &amp; interruption breakdown</div>
    """, unsafe_allow_html=True)

    # 7-day tiles
    day_cols = st.columns(7)
    for idx, d in enumerate(weekly_data["days"]):
        with day_cols[idx]:
            score_color = "var(--success)" if d['score'] >= 60 else "var(--attention)"
            st.markdown(f"""
            <div class="rf-day">
                <div style="font-size:12px;font-weight:700;color:var(--steel);text-transform:uppercase;">{d['short_day']}</div>
                <div style="font-family:'Montserrat',sans-serif;font-size:20px;font-weight:700;color:{score_color};margin:6px 0;">
                    {d['score']}%
                </div>
                <div style="font-size:11px;color:var(--stone);">{d['focus_hours']}h work</div>
                <div style="font-size:11px;color:var(--attention);margin-top:2px;">{d['interruptions']} drifts</div>
            </div>
            """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# ACTIVITY INQUIRY COPILOT
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

st.markdown("""
<div class="rf-card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div class="rf-title">Ask your work history</div>
        <span class="rf-badge rf-badge-cobalt">LOCAL LLM</span>
    </div>
    <div class="rf-sub" style="font-size:14px;">
        Query your daily workspace timeline, drift events, or draft handoff notes — all answered on-device.
    </div>
    <div style="height:16px;"></div>
""", unsafe_allow_html=True)

for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_query = st.chat_input("Ask about your work context (e.g., 'What caused my longest break today?')")

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
<div style="display:flex;justify-content:space-between;align-items:center;padding:28px 0 12px 0;border-top:1px solid var(--hairline-soft);font-size:12px;color:var(--stone);">
    <span class="rf-mono">REFOCUS ENGINE · PRIVATE ON-DEVICE TELEMETRY</span>
    <span class="rf-mono">ZERO CLOUD TRANSMISSION · AIR-GAPPED</span>
</div>
""", unsafe_allow_html=True)
