# BrowsePilot Frontend Layout Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three frontend issues: chat input positioned at page top on first load, right panel fonts too small, screenshot area overflows viewport without internal scroll.

**Architecture:** CSS-only fix in `streamlit_app.py` — lock the main container to viewport height with flexbox, push chat input to bottom, enable internal scrolling in chat messages area and right monitoring panel, and increase right panel label font sizes from 10px to 13px.

**Tech Stack:** Streamlit, CSS injection via `st.markdown(unsafe_allow_html=True)`

---

## File Structure

- **Modify:** `browsepilot/frontend/streamlit_app.py` — CSS block (lines 13–125) + right panel fonts (lines 382–502)

All three problems share the same root cause: the page container is not constrained to viewport height, so all content flows in a single scrolling document. The fix applies CSS flexbox to lock the layout.

---

### Task 1: CSS Viewport Lock + Chat Input Bottom Fix + Screenshot Scroll Containment

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py:13-125` (CSS injection block)

**Rationale:** The three issues are CSS selectors in the same block. Testing requires restarting the Streamlit frontend, so they go in one task to avoid three restarts.

- [ ] **Step 1: Replace the CSS block with viewport-locked layout**

Replace the entire `CSS = """..."""` block (lines 14–123) with the version below. The changes:

1. Add `html, body, .stApp { height: 100vh; overflow: hidden }` — prevents page-level scrolling
2. `section.main { height: 100vh; overflow: hidden }` — locks main section
3. `section.main > .block-container` — flex column, fills height, `overflow: hidden`
4. `[data-testid="stHorizontalBlock"]` — `flex: 1; min-height: 0` to fill available space
5. `[data-testid="column"]` — flex column, `overflow: hidden`, remove the old column divider rule
6. `[data-testid="column"]:first-child > div[data-testid="stVerticalBlock"]` — `flex: 1; overflow-y: auto` for scrollable chat messages
7. `[data-testid="stChatInput"]` — `flex-shrink: 0` stays at bottom
8. `[data-testid="column"]:last-child` — `overflow-y: auto` for right panel internal scroll

```python
CSS = """
<style>
/* === Swiss Editorial Design Tokens === */
:root {
  --bg: #faf9f6;
  --surface: #fefdfb;
  --border: #d4cdc2;
  --card-border: #e8e0d4;
  --text-primary: #1a1a1a;
  --text-body: #4a4238;
  --text-muted: #8b7f6e;
  --text-disabled: #c4b5a5;
  --accent: #e33e2b;
}

/* === Viewport Lock === */
html, body, .stApp {
  height: 100vh;
  overflow: hidden;
}

section.main {
  height: 100vh;
  overflow: hidden;
}

section.main > .block-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-top: 1rem;
  padding-bottom: 1rem;
}

/* Horizontal block fills available height */
[data-testid="stHorizontalBlock"] {
  flex: 1;
  min-height: 0;
}

/* Columns are flex columns, no page-level overflow */
[data-testid="column"] {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Column divider — moved to the column itself */
[data-testid="column"] + [data-testid="column"] {
  border-left: 1px solid var(--border);
}

/* === Left Column: Chat === */
/* Inner vertical block scrolls (chat messages), input stays at bottom */
[data-testid="column"]:first-child > div[data-testid="stVerticalBlock"] {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* Chat input sticks to bottom */
[data-testid="stChatInput"] {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

/* === Right Column: Monitoring Panel === */
[data-testid="column"]:last-child {
  overflow-y: auto;
}

/* === Typography === */
.stApp, .stMarkdown, .stChatMessage, .stChatInput, .stSelectbox {
  font-family: Georgia, 'Times New Roman', serif;
}

/* === Card styling === */
.stContainer, [data-testid="stVerticalBlock"] {
  border: 1px solid var(--card-border);
  border-radius: 0;
  background: var(--surface);
}

/* Chat messages — transparent background */
[data-testid="stChatMessage"] {
  background: transparent !important;
}

/* Selectbox */
.stSelectbox select {
  border: 1px solid var(--card-border) !important;
  background: var(--surface) !important;
  color: var(--text-body) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
  background: var(--bg);
  border-right: 1px solid var(--border);
}

[data-testid="stSidebarNav"] { display: none; }

/* === Animations === */
@keyframes fadeInOut {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.live-dot {
  display: inline-block;
  width: 5px; height: 5px;
  background: var(--accent);
  border-radius: 50%;
  animation: fadeInOut 1.5s ease-in-out infinite;
}

.thinking-dot {
  display: inline-block;
  width: 4px; height: 4px;
  background: var(--accent);
  border-radius: 50%;
  animation: fadeInOut 1s ease-in-out infinite;
  vertical-align: middle;
  margin-left: 6px;
}

/* Progress bar segments */
.progress-bar { display: flex; gap: 3px; margin-top: 8px; }
.progress-segment { height: 3px; flex: 1; background: var(--card-border); }
.progress-segment.done { background: var(--accent); }
.progress-segment.active { background: var(--accent); animation: fadeInOut 1s ease-in-out infinite; }

/* Phase label */
.phase-label {
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-bottom: 6px;
  font-family: Georgia, serif;
}

/* Plan card step line */
.plan-step { line-height: 2; font-size: 12px; }
.plan-step.done { color: var(--text-disabled); text-decoration: line-through; }
.plan-step.current { color: var(--accent); font-weight: 600; font-style: italic; border-left: 2px solid var(--accent); padding-left: 8px; }
.plan-step.pending { color: var(--text-muted); }

/* === Right Column: Scrollbar === */
[data-testid="column"]:last-child::-webkit-scrollbar {
  width: 4px;
}
[data-testid="column"]:last-child::-webkit-scrollbar-thumb {
  background: var(--card-border);
  border-radius: 2px;
}
</style>
"""
```

- [ ] **Step 2: Restart Streamlit frontend and verify**

Run: `cd D:\AI_Agent_Demo && start /b browsepilot/frontend/run.bat` (or equivalent)

Verify:
- First load: chat input appears at viewport bottom, not top
- Send several messages: chat messages scroll internally, input stays at bottom
- Right panel: internal scrollbar when content overflows
- Screenshot display: scrolls within right panel, not whole page

- [ ] **Step 3: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "fix: lock viewport layout, pin chat input to bottom, add scroll containment"
```

---

### Task 2: Right Panel Font Size Increase

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py:390-471` (right panel inline styles)

- [ ] **Step 1: Increase section label font sizes from 10px to 13px**

Four labels need updating in the right panel. Replace each `font-size:10px` in the section headers with `font-size:13px` and add `font-weight:700`:

**Plan header** (line ~393):
```python
# Old:
'text-transform:uppercase">执行计划</span>'
# New:
'text-transform:uppercase;font-weight:700">执行计划</span>'
```

**Token header** (line ~426):
```python
# Old:
'text-transform:uppercase">Token</span>'
# New:
'text-transform:uppercase;font-weight:700">Token</span>'
```

Also increase token body font from `font-size:11px` to `font-size:13px`:
```python
# Old:
'<div style="font-size:11px;line-height:2.2;color:#8b7f6e;margin-top:8px">'
# New:
'<div style="font-size:13px;line-height:2.2;color:#8b7f6e;margin-top:8px">'
```

**Screenshot header** (line ~439):
```python
# Old:
'text-transform:uppercase">实时截图</span>'
# New:
'text-transform:uppercase;font-weight:700">实时截图</span>'
```

**Replay header** (line ~469):
```python
# Old:
'text-transform:uppercase;font-family:Georgia,serif">操作回放</span>'
# New:
'text-transform:uppercase;font-family:Georgia,serif;font-weight:700">操作回放</span>'
```

Also update the empty plan state (line ~413):
```python
# Old:
'text-transform:uppercase;font-family:Georgia,serif">执行计划</span>'
# New:
'text-transform:uppercase;font-family:Georgia,serif;font-weight:700">执行计划</span>'
```

Note: The `font-size:10px` is set in the CSS `.phase-label` class at 10px — keep that for chat thinking indicators. The right panel uses inline styles which override CSS classes. Change the inline `font-size:10px` to `font-size:13px` for the 4 section labels, plus the empty state label.

- [ ] **Step 2: Verify visual result**

Restart Streamlit, confirm right panel labels are larger and more prominent.

- [ ] **Step 3: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "fix: increase right panel label font size from 10px to 13px"
```

---

## Verification Checklist

After both tasks:

- [ ] First page load: chat input at viewport bottom
- [ ] 10+ messages: chat area scrolls, input stays fixed
- [ ] Right panel: labels readable, fonts prominent
- [ ] Screenshot present: scrolls within right panel
- [ ] Replay section: accessible via right panel scroll
- [ ] Plan card + Token card: visible in right panel top row
- [ ] Sidebar: still functional, no layout breakage
- [ ] No horizontal scrollbar on the page
