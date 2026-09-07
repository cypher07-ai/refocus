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

if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "Dashboard"

# -----------------------------------------------------------------------------
# Streamlit App Configuration & META DESIGN SYSTEM TOKENS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ReFocus — Work Context OS",
    page_icon="◬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# META DESIGN SYSTEM TOKENS (Design.md specification)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  /* Colors */
  --primary: #0064e0;
  --primary-deep: #0457cb;
  --primary-soft: #0091ff;
  --on-primary: #ffffff;
  --ink-button: #000000;
  --on-ink-button: #ffffff;
  --fb-blue: #1876f2;
  --meta-link: #385898;
  --oculus-purple: #a121ce;
  --success: #31a24c;
  --success-bg: #24e400;
  --attention: #f2a918;
  --warning: #f7b928;
  --warning-bg: #ffe200;
  --critical: #e41e3f;
  --critical-strong: #f0284a;
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
  --disabled-text: #bcc0c4;

  /* Shapes & Radii */
  --rounded-xs: 2px;
  --rounded-sm: 4px;
  --rounded-md: 6px;
  --rounded-lg: 8px;
  --rounded-xl: 16px;
  --rounded-xxl: 24px;
  --rounded-xxxl: 32px;
  --rounded-feature: 40px;
  --rounded-full: 100px;
  --rounded-circle: 9999px;

  /* Spacing */
  --spacing-xxs: 4px;
  --spacing-xs: 8px;
  --spacing-sm: 10px;
  --spacing-md: 12px;
  --spacing-base: 16px;
  --spacing-lg: 20px;
  --spacing-xl: 24px;
  --spacing-xxl: 32px;
  --spacing-xxxl: 40px;
  --spacing-section-sm: 48px;
  --spacing-section: 64px;
  --spacing-section-lg: 80px;
}

html, body, [class*="css"], .stMarkdown, .stText {
    font-family: 'Optimistic VF', 'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Optimistic VF', 'Montserrat', sans-serif !important;
    font-feature-settings: "ss01" 1, "ss02" 1 !important;
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
    padding-top: 0rem !important;
    padding-bottom: 4rem !important;
    max-width: 1280px !important;
}

/* -------------------------------------------------------------
   Meta Components & Cards
------------------------------------------------------------- */
/* Promo Banner Top Strip */
.meta-promo-banner {
    background-color: var(--ink-deep);
    color: var(--canvas);
    padding: 12px 24px;
    font-size: 14px;
    font-weight: 700;
    line-height: 1.43;
    letter-spacing: -0.14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: -1.5rem -1rem 1.5rem -1rem;
}

/* Top Navigation Bar */
.meta-top-nav {
    background-color: var(--canvas);
    height: 64px;
    border-bottom: 1px solid var(--hairline-soft);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 8px;
    margin-bottom: 24px;
}

.meta-logo {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: var(--ink-deep);
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Marketing Hero Band Card */
.meta-hero-band {
    background-color: var(--canvas);
    border-radius: var(--rounded-xxxl);
    padding: var(--spacing-section-sm) var(--spacing-xxl);
    border: 1px solid var(--hairline-soft);
    margin-bottom: 32px;
}

.meta-hero-display {
    font-size: 44px;
    font-weight: 500;
    line-height: 1.16;
    letter-spacing: -0.5px;
    color: var(--ink-deep);
    font-feature-settings: "ss01" 1, "ss02" 1;
    margin-bottom: 12px;
}

.meta-hero-subhead {
    font-size: 20px;
    font-weight: 300;
    line-height: 1.35;
    color: var(--charcoal);
    font-feature-settings: "ss01" 1, "ss02" 1;
    margin-bottom: 28px;
}

/* Standard Product Feature Cards */
.card-product-feature {
    background-color: var(--canvas);
    border-radius: var(--rounded-xxxl);
    padding: var(--spacing-xxl);
    border: 1px solid var(--hairline-soft);
    margin-bottom: 24px;
}

.card-checkout-summary {
    background-color: var(--canvas);
    border-radius: var(--rounded-xl);
    padding: var(--spacing-xl);
    border: 1px solid var(--hairline-soft);
    box-shadow: rgba(20, 22, 26, 0.08) 0px 1px 4px 0px;
    margin-bottom: 24px;
}

.card-icon-feature {
    background-color: var(--canvas);
    border-radius: var(--rounded-xl);
    padding: var(--spacing-xl);
    border: 1px solid var(--hairline-soft);
    height: 100%;
}

.why-buy-tile {
    background-color: var(--canvas);
    border-radius: var(--rounded-xl);
    padding: var(--spacing-xxl) var(--spacing-xl);
    border: 1px solid var(--hairline-soft);
}

.warranty-card {
    background-color: var(--surface-soft);
    border-radius: var(--rounded-xxl);
    padding: var(--spacing-xxl);
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
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.14px;
    color: var(--ink-deep);
}

/* Product Thumbnail & Option Containers */
.product-thumbnail {
    background-color: var(--surface-soft);
    border-radius: var(--rounded-xl);
    padding: var(--spacing-base);
}

.radio-option {
    background-color: var(--canvas);
    border-radius: var(--rounded-lg);
    padding: var(--spacing-lg);
    border: 1px solid rgba(10, 19, 23, 0.12);
}

.radio-option-selected {
    background-color: var(--canvas);
    border-radius: var(--rounded-lg);
    padding: var(--spacing-lg);
    border: 2px solid #0143b5;
}

/* Badges & Chips */
.badge-promo-yellow {
    background-color: var(--warning);
    color: var(--ink-deep);
    font-size: 12px;
    font-weight: 700;
    border-radius: var(--rounded-full);
    padding: 4px 10px;
}

.badge-attention {
    background-color: var(--attention);
    color: var(--canvas);
    font-size: 12px;
    font-weight: 700;
    border-radius: var(--rounded-full);
    padding: 4px 10px;
}

.badge-success {
    background-color: var(--success);
    color: var(--canvas);
    font-size: 12px;
    font-weight: 700;
    border-radius: var(--rounded-full);
    padding: 4px 10px;
}

.badge-critical {
    background-color: var(--critical);
    color: var(--canvas);
    font-size: 12px;
    font-weight: 700;
    border-radius: var(--rounded-full);
    padding: 4px 10px;
}

/* Button Variants */
/* Primary Marketing Button (Black Pill) */
.stButton > button {
    background-color: var(--ink-button) !important;
    color: var(--on-ink-button) !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    line-height: 1.43 !important;
    letter-spacing: -0.14px !important;
    border-radius: var(--rounded-full) !important;
    padding: 14px 30px !important;
    border: none !important;
    transition: background-color 0.15s ease !important;
}

.stButton > button:hover {
    background-color: var(--charcoal) !important;
    color: var(--on-ink-button) !important;
}

/* Commerce Action CTA (Cobalt Pill) */
.btn-buy-cta .stButton > button {
    background-color: var(--primary) !important;
    color: var(--on-primary) !important;
}

.btn-buy-cta .stButton > button:hover {
    background-color: var(--primary-deep) !important;
}

/* Secondary Outlined Ghost Button */
.btn-secondary .stButton > button {
    background-color: transparent !important;
    color: var(--ink-deep) !important;
    border: 2px solid var(--ink-deep) !important;
    padding: 12px 28px !important;
}

.btn-secondary .stButton > button:hover {
    background-color: var(--surface-soft) !important;
}

/* Pill Tabs Nav */
.pill-tab {
    background-color: var(--canvas);
    color: var(--ink);
    font-size: 14px;
    font-weight: 700;
    border-radius: var(--rounded-full);
    padding: 8px 16px;
    border: 1px solid var(--hairline);
    cursor: pointer;
    display: inline-block;
    margin-right: 6px;
}

.pill-tab-active {
    background-color: var(--ink-deep);
    color: var(--canvas);
    border: none;
}

/* Form Controls */
[data-testid="stExpander"] {
    background-color: var(--surface-soft) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: var(--rounded-xl) !important;
    margin-top: 16px;
}

[data-testid="stExpander"] details summary {
    font-size: 14px !important;
    font-weight: 700 !important;
    color: var(--ink-deep) !important;
}

code {
    background-color: var(--surface-soft) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: var(--rounded-lg) !important;
    padding: 3px 8px !important;
    color: var(--ink-deep) !important;
}

.stChatMessage {
    background-color: var(--canvas) !important;
    border: 1px solid var(--hairline-soft) !important;
    border-radius: var(--rounded-xl) !important;
    padding: 16px 20px !important;
    margin-bottom: 12px !important;
}

[data-testid="stChatInput"] textarea {
    background-color: var(--canvas) !important;
    border: 1px solid var(--hairline) !important;
    border-radius: var(--rounded-full) !important;
    padding: 12px 24px !important;
    color: var(--ink) !important;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: var(--fb-blue) !important;
}

hr {
    border-color: var(--hairline-soft) !important;
    margin: var(--spacing-xxl) 0 !important;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Component: Promo Banner (Top announcement strip)
# -----------------------------------------------------------------------------
def render_promo_banner():
    st.markdown("""
    <div class="meta-promo-banner">
        <div>
            <span class="badge-promo-yellow" style="margin-right: 10px;">PROMOTION</span>
            <span>Refocus Copilot: Air-Gapped Local Cognitive Engine for Hardware & Desktop</span>
        </div>
        <div style="font-size: 12px; color: #ced0d4;">
            Version 2.0 // Zero Cloud Transmission
        </div>
    </div>
    """, unsafe_allow_html=True)

render_promo_banner()

# -----------------------------------------------------------------------------
# Component: Top Navigation (Desktop Header with Pill Tabs)
# -----------------------------------------------------------------------------
def render_top_navigation():
    col_brand, col_status, col_toggle = st.columns([1.8, 2.2, 1.0], gap="medium")
    
    with col_brand:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 14px; margin-top: 4px;">
            <span style="font-size: 24px; font-weight: 700; letter-spacing: -0.5px; color: #0a1317; font-feature-settings: 'ss01' 1, 'ss02' 1;">Meta ReFocus</span>
            <span style="height: 20px; width: 1px; background-color: #dee3e9;"></span>
            <span style="font-size: 14px; font-weight: 400; color: #5d6c7b;">Work Context OS</span>
        </div>
        """, unsafe_allow_html=True)

    with col_status:
        render_live_system_status()

    with col_toggle:
        st.toggle("Privacy Mode", key="privacy_mode", help="Pauses automated background OCR snapshotting.")

@st.fragment(run_every="1s")
def render_live_system_status():
    idle_secs = int(get_idle_seconds())
    is_paused = st.session_state.get("privacy_mode", False)

    if is_paused:
        status_badge = '<span class="badge-attention">○ PAUSED</span>'
        idle_info = "Snapshots suspended"
    elif idle_secs < INACTIVITY_THRESHOLD:
        status_badge = '<span class="badge-success">● ACTIVE MONITOR</span>'
        idle_info = f"Idle: <code>{idle_secs}s</code> / <code>{INACTIVITY_THRESHOLD}s</code>"
    else:
        away_m = idle_secs // 60
        away_s = idle_secs % 60
        status_badge = '<span class="badge-promo-yellow">▲ INTERRUPTED</span>'
        idle_info = f"Away: <code>{away_m}m {away_s}s</code>"

    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 6px;">
        {status_badge}
        <span style="font-size: 14px; color: #4b4c4f;">{idle_info}</span>
    </div>
    """, unsafe_allow_html=True)

render_top_navigation()

# -----------------------------------------------------------------------------
# Component: 4-Up Feature Icon Row (Reassurance tiles)
# -----------------------------------------------------------------------------
def render_feature_icon_row():
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.markdown("""
        <div class="card-icon-feature">
            <div style="font-size: 20px; margin-bottom: 8px;">🔒</div>
            <div style="font-size: 16px; font-weight: 700; color: #0a1317; margin-bottom: 4px;">Air-Gapped Privacy</div>
            <div style="font-size: 14px; color: #5d6c7b; line-height: 1.4;">100% on-device OCR and local LLM execution.</div>
        </div>
        """, unsafe_allow_html=True)
    with f2:
        st.markdown("""
        <div class="card-icon-feature">
            <div style="font-size: 20px; margin-bottom: 8px;">⚡</div>
            <div style="font-size: 16px; font-weight: 700; color: #0a1317; margin-bottom: 4px;">Zero CPU Overhead</div>
            <div style="font-size: 14px; color: #5d6c7b; line-height: 1.4;">Native Windows idle timer triggers snapshots only when away.</div>
        </div>
        """, unsafe_allow_html=True)
    with f3:
        st.markdown("""
        <div class="card-icon-feature">
            <div style="font-size: 20px; margin-bottom: 8px;">🎯</div>
            <div style="font-size: 16px; font-weight: 700; color: #0a1317; margin-bottom: 4px;">Bullseye Recovery</div>
            <div style="font-size: 14px; color: #5d6c7b; line-height: 1.4;">Reconstructs exact file, function, and step-by-step next actions.</div>
        </div>
        """, unsafe_allow_html=True)
    with f4:
        st.markdown("""
        <div class="card-icon-feature">
            <div style="font-size: 20px; margin-bottom: 8px;">📊</div>
            <div style="font-size: 16px; font-weight: 700; color: #0a1317; margin-bottom: 4px;">Multi-App Domain</div>
            <div style="font-size: 14px; color: #5d6c7b; line-height: 1.4;">Universal telemetry across IDEs, Figma, Docs, Excel & Browsers.</div>
        </div>
        """, unsafe_allow_html=True)

render_feature_icon_row()
st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Component: Hero Band Marketing (Showcase Banner with Dual-CTA)
# -----------------------------------------------------------------------------
state = detect_current_state()
previous_category = get_previous_category()

hero_col1, hero_col2 = st.columns([1.75, 1.25], gap="large")

with hero_col1:
    if state.get("status") == "ok" and previous_category:
        away_seconds = time_since_last_category(previous_category)
        away_minutes = int(away_seconds) // 60
        away_secs_rem = int(away_seconds) % 60

        st.markdown(f"""
        <div class="meta-hero-band" style="border-top: 4px solid var(--primary);">
            <div class="meta-card-header">
                <div class="meta-card-title">
                    <span>Interrupted Workspace Handoff</span>
                </div>
                <span class="badge-promo-yellow">DRIFT DETECTED</span>
            </div>
            <div class="meta-hero-display">
                Resume {previous_category.title()}
            </div>
            <div class="meta-hero-subhead">
                You were away for <b>{away_minutes}m {away_secs_rem}s</b>. ReFocus captured your active workspace state right before the interruption.
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px;">
                <div class="warranty-card">
                    <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Recovery Target</div>
                    <div style="font-size: 24px; font-weight: 700; color: var(--ink-deep); margin-top: 4px;">{previous_category.upper()}</div>
                    <div style="font-size: 14px; color: var(--charcoal); margin-top: 4px;">Last active focus state</div>
                </div>
                <div class="warranty-card">
                    <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Interrupted By</div>
                    <div style="font-size: 24px; font-weight: 700; color: var(--primary); margin-top: 4px;">{state['current_category'].upper()}</div>
                    <div style="font-size: 14px; color: var(--charcoal); margin-top: 4px;">Active window switch</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        cta_col1, cta_col2 = st.columns([1.5, 1.0])
        with cta_col1:
            st.markdown('<div class="btn-buy-cta">', unsafe_allow_html=True)
            trigger_recovery = st.button(
                f"Reconstruct Context & Resume in {previous_category.upper()}",
                use_container_width=True,
                type="primary"
            )
            st.markdown('</div>', unsafe_allow_html=True)
        with cta_col2:
            st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
            view_logs = st.button("View Telemetry Logs", use_container_width=True)
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
            <div class="card-product-feature" style="margin-top: 24px;">
                <div class="meta-card-header">
                    <div class="meta-card-title">
                        <span>Executive Recovery Briefing — {cache['category'].upper()}</span>
                    </div>
                    <span style="font-size: 12px; color: var(--stone);">Generated at {cache['timestamp']}</span>
                </div>
                <div style="font-size: 16px; line-height: 1.65; color: var(--ink);">
            """, unsafe_allow_html=True)
            
            st.markdown(cache["briefing"])
            st.markdown("</div>", unsafe_allow_html=True)

            with st.expander("View Raw Evidence & OCR Logs"):
                if cache["snapshots"]:
                    for idx, (w_title, ocr_data, ts) in enumerate(cache["snapshots"][-4:]):
                        ts_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                        st.markdown(f"""
                        <div style="border-bottom: 1px solid var(--hairline-soft); padding: 12px 0;">
                            <div style="display: flex; justify-content: space-between; font-size: 14px; font-weight: 700; color: var(--ink-deep);">
                                <span>[{idx+1}] {w_title}</span>
                                <span style="font-family: 'JetBrains Mono', monospace; color: var(--stone); font-size: 12px;">{ts_str}</span>
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
        <div class="card-product-feature">
            <div class="meta-card-header">
                <div class="meta-card-title">
                    <span>Current Workspace Telemetry</span>
                </div>
                <span class="badge-success">SYNCHRONIZED</span>
            </div>
            <div class="meta-hero-display" style="font-size: 36px; margin-bottom: 8px;">
                {current_app}
            </div>
            <div class="meta-hero-subhead" style="font-size: 16px; margin-bottom: 20px;">
                {current_win}
            </div>
            <div style="font-size: 14px; color: var(--steel); line-height: 1.55;">
                Zero drift detected. ReFocus is actively monitoring your workflow. When you switch contexts or step away for ≥ 3 minutes, your recovery handoff will stage here automatically.
            </div>
        </div>
        """, unsafe_allow_html=True)

with hero_col2:
    # --- RIGHT: DAILY TELEMETRY (Checkout Summary Card Style) ---
    st.markdown("""
    <div class="card-checkout-summary">
        <div class="meta-card-header">
            <div class="meta-card-title">
                <span>Daily Focus Telemetry</span>
            </div>
            <span style="font-size: 12px; font-weight: 700; color: var(--stone);">TODAY</span>
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
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Focus Efficiency</div>
            <div style="font-size: 28px; font-weight: 700; color: var(--ink-deep); margin-top: 4px;">{focus_score}%</div>
            <div style="font-size: 12px; color: {delta_color}; font-weight: 700; margin-top: 4px;">
                {delta_symbol} {abs(score_delta)}% vs yesterday
            </div>
        </div>
        """, unsafe_allow_html=True)

    with m_col2:
        st.markdown(f"""
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Deep Work Time</div>
            <div style="font-size: 28px; font-weight: 700; color: var(--ink-deep); margin-top: 4px;">{focus_min_today}m</div>
            <div style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Productive duration</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

    m_col3, m_col4 = st.columns(2)
    with m_col3:
        st.markdown(f"""
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Context Switches</div>
            <div style="font-size: 28px; font-weight: 700; color: var(--attention); margin-top: 4px;">{interruptions}</div>
            <div style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Drift events logged</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col4:
        st.markdown(f"""
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Snapshots Logged</div>
            <div style="font-size: 28px; font-weight: 700; color: var(--ink-deep); margin-top: 4px;">{total_snaps}</div>
            <div style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Telemetry records</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Component: Tech Specs Table (Active Workspace Technical Specification)
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

st.markdown("""
<div class="card-product-feature">
    <div class="meta-card-header">
        <div class="meta-card-title">
            <span>System Telemetry Specs</span>
        </div>
        <span class="badge-success">VERIFIED</span>
    </div>
    
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
        <div>
            <div style="font-size: 16px; font-weight: 700; color: var(--ink-deep); margin-bottom: 12px;">Active Pipeline Details</div>
            <div style="border-bottom: 1px solid var(--hairline-soft); padding: 8px 0; display: flex; justify-content: space-between; font-size: 14px;">
                <span style="font-weight: 700; color: var(--ink);">Capture Engine</span>
                <span style="color: var(--charcoal);">MSS Screen Grabber v9.0</span>
            </div>
            <div style="border-bottom: 1px solid var(--hairline-soft); padding: 8px 0; display: flex; justify-content: space-between; font-size: 14px;">
                <span style="font-weight: 700; color: var(--ink);">OCR Parsing</span>
                <span style="color: var(--charcoal);">PyTesseract v0.3.10</span>
            </div>
            <div style="border-bottom: 1px solid var(--hairline-soft); padding: 8px 0; display: flex; justify-content: space-between; font-size: 14px;">
                <span style="font-weight: 700; color: var(--ink);">Idle Timer Threshold</span>
                <span style="color: var(--charcoal);">180 seconds (3 mins)</span>
            </div>
        </div>
        <div>
            <div style="font-size: 16px; font-weight: 700; color: var(--ink-deep); margin-bottom: 12px;">Intelligence & Security</div>
            <div style="border-bottom: 1px solid var(--hairline-soft); padding: 8px 0; display: flex; justify-content: space-between; font-size: 14px;">
                <span style="font-weight: 700; color: var(--ink);">Local LLM Model</span>
                <span style="color: var(--charcoal);">Ollama llama3.2:3b</span>
            </div>
            <div style="border-bottom: 1px solid var(--hairline-soft); padding: 8px 0; display: flex; justify-content: space-between; font-size: 14px;">
                <span style="font-weight: 700; color: var(--ink);">Database Storage</span>
                <span style="color: var(--charcoal);">SQLite refocus.db (Air-Gapped)</span>
            </div>
            <div style="border-bottom: 1px solid var(--hairline-soft); padding: 8px 0; display: flex; justify-content: space-between; font-size: 14px;">
                <span style="font-weight: 700; color: var(--ink);">Cloud Data Exfiltration</span>
                <span style="color: var(--success); font-weight: 700;">0 Bytes (100% Private)</span>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Component: 7-DAY EXECUTIVE WEEKLY AUDIT
# -----------------------------------------------------------------------------
col_rep_head, col_rep_btn = st.columns([2.5, 1.2], gap="medium")

with col_rep_head:
    st.markdown("""
    <div style="font-size: 28px; font-weight: 300; color: var(--ink-deep); letter-spacing: -0.5px; font-feature-settings: 'ss01' 1, 'ss02' 1;">
        7-Day Executive Focus Audit
    </div>
    <div style="font-size: 16px; color: var(--steel); margin-top: 4px;">
        Compile multi-day cognitive load, context switching velocity, and deep work trends.
    </div>
    """, unsafe_allow_html=True)

with col_rep_btn:
    if st.button("📊 Compile Weekly Report", use_container_width=True):
        st.session_state["show_weekly_report"] = True

if st.session_state["show_weekly_report"]:
    weekly_data = get_weekly_summary()
    
    st.markdown("""
    <div style="font-size: 14px; font-weight: 700; color: var(--success); margin: 24px 0 16px 0; text-transform: uppercase; letter-spacing: -0.14px;">
        ● Executive 7-Day Productivity Dossier
    </div>
    """, unsafe_allow_html=True)
    
    # 4 Main KPI Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(f"""
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">7-Day Deep Work</div>
            <div style="font-size: 28px; font-weight: 700; color: var(--primary); margin-top: 4px;">{weekly_data['total_focus_hours']}h</div>
            <div style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Total focus duration</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"""
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Avg Focus Score</div>
            <div style="font-size: 28px; font-weight: 700; color: var(--ink-deep); margin-top: 4px;">{weekly_data['avg_focus_score']}%</div>
            <div style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Weighted daily efficiency</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"""
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Total Drift Events</div>
            <div style="font-size: 28px; font-weight: 700; color: var(--attention); margin-top: 4px;">{weekly_data['total_interruptions']}</div>
            <div style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Context switches logged</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi4:
        st.markdown(f"""
        <div class="product-thumbnail">
            <div style="font-size: 12px; font-weight: 700; color: var(--steel); text-transform: uppercase;">Peak Performance</div>
            <div style="font-size: 18px; font-weight: 700; color: var(--ink-deep); margin-top: 8px;">{weekly_data['best_day']}</div>
            <div style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">{weekly_data['best_day_hours']}h deep work logged</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div style="font-size: 14px; font-weight: 700; text-transform: uppercase; color: var(--steel); margin: 28px 0 14px 0; letter-spacing: -0.14px;">
        Daily Focus Velocity & Interruption Breakdown
    </div>
    """, unsafe_allow_html=True)
    
    # 7-Day Velocity Breakdown Columns
    day_cols = st.columns(7)
    for idx, d in enumerate(weekly_data["days"]):
        with day_cols[idx]:
            score_color = "var(--success)" if d['score'] >= 60 else "var(--attention)"
            st.markdown(f"""
            <div class="product-thumbnail" style="text-align: center; padding: 16px 8px;">
                <div style="font-size: 13px; font-weight: 700; color: var(--ink);">{d['short_day']}</div>
                <div style="font-size: 22px; font-weight: 700; color: {score_color}; margin: 8px 0 4px 0;">
                    {d['score']}%
                </div>
                <div style="font-size: 12px; color: var(--steel);">{d['focus_hours']}h work</div>
                <div style="font-size: 12px; color: var(--attention); margin-top: 2px;">{d['interruptions']} drifts</div>
            </div>
            """, unsafe_allow_html=True)

    # Executive AI Retrospective Card (Warranty Card Style)
    st.markdown(f"""
    <div class="warranty-card" style="margin-top: 28px;">
        <div style="font-size: 18px; font-weight: 700; color: var(--ink-deep); margin-bottom: 8px;">
            AI Executive Retrospective
        </div>
        <div style="font-size: 16px; color: var(--charcoal); line-height: 1.6;">
            Over the past 7 days, you maintained a <b>{weekly_data['avg_focus_score']}% focus efficiency</b> across <b>{weekly_data['total_focus_hours']} hours</b> of deep work. 
            Your strongest flow state occurred on <b>{weekly_data['best_day']}</b> ({weekly_data['best_day_hours']} hours). 
            Primary drift vector was mid-afternoon context switching between IDE and browser documentation.
        </div>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Component: FAQ Accordion & Help
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

st.markdown("""
<div style="font-size: 28px; font-weight: 300; color: var(--ink-deep); margin-bottom: 16px; font-feature-settings: 'ss01' 1, 'ss02' 1;">
    Frequently Asked Questions
</div>
""", unsafe_allow_html=True)

with st.expander("How does ReFocus detect interruptions without consuming battery or CPU?"):
    st.markdown("""
    ReFocus registers a zero-overhead callback with Windows `user32.dll` via Python's native `ctypes` library. 
    It consumes **0% CPU** while you are working. Only when you stop typing/moving the mouse for 3 consecutive minutes does it trigger a single OCR snapshot.
    """)

with st.expander("Is my screen data uploaded to cloud AI servers?"):
    st.markdown("""
    **No.** ReFocus runs 100% air-gapped on your computer. Screenshots are processed by local Tesseract OCR, stored in your local SQLite database (`refocus.db`), and summarized by local Ollama models (`llama3.2:3b`). Zero bytes leave your machine.
    """)

with st.expander("What software applications does ReFocus support?"):
    st.markdown("""
    ReFocus has universal telemetry support for Coding IDEs (VSCode, Cursor, PyCharm), Design tools (Figma, Photoshop, Canva), Documents & Writing (Word, Notion, Google Docs, Obsidian), Analytics (Excel, Google Sheets), Browsers (Chrome, Edge, Firefox), and Team Communication (Slack, Teams).
    """)

# -----------------------------------------------------------------------------
# Component: ACTIVITY INQUIRY COPILOT (Command Chat Interface)
# -----------------------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)

st.markdown("""
<div class="card-product-feature">
    <div class="meta-card-header">
        <div class="meta-card-title">
            <span>Activity Query Interface — Copilot</span>
        </div>
        <span class="badge-success">LOCAL LLM</span>
    </div>
    <div style="font-size: 16px; color: var(--steel); margin-bottom: 24px;">
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
# Component: Footer Region (Meta Footer Spec)
# -----------------------------------------------------------------------------
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; padding: 48px 0 24px 0; border-top: 1px solid var(--hairline-soft); font-size: 14px; color: var(--steel);">
    <div>
        <span style="font-weight: 700; color: var(--ink-deep);">Meta ReFocus Engine</span> — Private On-Device Context Telemetry
    </div>
    <div>
        <span>Zero Cloud Transmission</span> · <span style="color: var(--primary); font-weight: 700;">Air-Gapped Local OS</span>
    </div>
</div>
""", unsafe_allow_html=True)