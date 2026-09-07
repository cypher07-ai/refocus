import sys
import os
import datetime

try:
    import ollama
except ImportError:
    ollama = None

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db import get_recent_snapshots
from sessions.session_engine import get_last_session_snapshots, categorize_window

def clean_snapshot_text(text, max_chars=2000):
    if not text:
        return "[No textual content extracted from screen]"
    return text.strip()[:max_chars]

def build_chronological_context(snapshots):
    context_blocks = []
    total_snaps = len(snapshots)

    for idx, (window_title, ocr_text, timestamp) in enumerate(snapshots):
        time_str = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        is_final = (idx == total_snaps - 1)
        tag = ">>> [MOMENT OF INTERRUPTION - FINAL ACTIVE STATE]" if is_final else f"Step {idx+1}/{total_snaps}"
        
        cleaned = clean_snapshot_text(ocr_text)
        block = (
            f"=== {tag} at {time_str} ===\n"
            f"Active Window: {window_title}\n"
            f"Screen Content / Visible Data:\n{cleaned}\n"
        )
        context_blocks.append(block)

    return "\n".join(context_blocks)

def generate_briefing_for_category(target_category, model="llama3.2:3b"):
    snapshots = get_last_session_snapshots(target_category)

    if not snapshots:
        return f"⚠️ **INSUFFICIENT TELEMETRY:** Not enough snapshots recorded for `{target_category}` to construct a precision recovery briefing."

    timeline_context = build_chronological_context(snapshots)

    prompt = f"""You are ReFocus Precision Context Engine, a multi-application cognitive recovery system.
Analyze the following chronological screen snapshots captured in the workspace category: '{target_category.upper()}'.

Adapt your analysis to the specific software being used:
- If Design (Figma, Photoshop, Canva): Identify active artboard, layer, UI screen, or color/component changes.
- If Documents/Writing (Word, Docs, Notion, Obsidian): Identify document title, active paragraph/heading, and draft ideas.
- If Analytics/Spreadsheets (Excel, Sheets, PowerBI): Identify sheet name, active table, formulas, or numbers being analyzed.
- If Research/Browsing: Identify specific article title, query, documentation page, or key finding.
- If Coding/Terminal: Identify active file, function, line number, stack trace, and terminal outputs.
- If Communication (Slack, Teams, Email): Identify sender, thread topic, and pending replies.

Provide a high-precision, actionable briefing in these 4 structured sections:

### 🎯 1. EXACT POINT OF INTERRUPTION
- **Target Application / Document:** [Exact document, artboard, spreadsheet, or window title]
- **Active Focus Area:** [Specific section, layer, formula, function, or paragraph being worked on]
- **Last Observed State:** [What was actively on screen at the exact moment of interruption]

### 🧠 2. WORKING OBJECTIVE & COGNITIVE TRAIL
- [2-3 sentences explaining the exact task, problem being solved, or goal of this work session]

### 🔍 3. FORENSIC EVIDENCE ARTIFACTS
- **Extracted Content / Data:** [Quote visible sentences, error messages, formulas, or data points from OCR]
- **Context Identifiers:** [Key file names, URLs, sheet names, or thread topics visible]

### ⚡ 4. BULLSEYE RESUME ACTIONS
1. **[Immediate Action]:** [Exact step to reopen/refocus the specific document or app]
2. **[Next Task Item]:** [Concrete next action to continue thought flow]
3. **[Verification]:** [How to confirm your work state is complete/saved]

Snapshots Timeline:
{timeline_context}
"""

    if ollama is not None:
        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2}
            )
            return response["message"]["content"]
        except Exception:
            pass

    # High-precision heuristic fallback if Ollama is offline or not installed
    final_window = snapshots[-1][0]
    final_text = snapshots[-1][1][:500] if snapshots[-1][1] else "No text extracted"
    return f"""*(Ollama offline — displaying multi-application heuristic summary)*

### 🎯 1. EXACT POINT OF INTERRUPTION
- **Target Application / Workspace:** `{final_window}`
- **Domain Category:** `{target_category.upper()}`
- **Last Observed State:** Active in `{final_window}` prior to interruption.

### 🔍 2. FORENSIC SCREEN EXTRACT
```text
{final_text}
```

### ⚡ 3. BULLSEYE RESUME ACTIONS
1. **Switch Window:** Bring `{final_window}` back to focus.
2. **Resume Flow:** Continue editing from the extracted section above.
3. **Verify:** Check your last draft, edits, or calculations."""

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print("Testing universal briefing engine...")
    res = generate_briefing_for_category("coding")
    print(res)