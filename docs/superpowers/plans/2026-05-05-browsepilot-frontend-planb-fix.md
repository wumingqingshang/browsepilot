# BrowsePilot Frontend Plan B Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix chat scrolling + input positioning, right panel screenshot scroll, token card squeeze, and increase right panel label font sizes.

**Architecture:** Replace fragile `:first-child` / `:last-child` deep-nested CSS selectors with semantic `:has()` selectors that target "the column containing the chat input" rather than positional indices. Keep viewport lock foundation. Right panel fixes are targeted inline style and CSS adjustments.

**Tech Stack:** Streamlit 1.35+, CSS `:has()` selector (supported in all modern browsers)

---

## File Structure

- **Modify:** `browsepilot/frontend/streamlit_app.py` — CSS block (lines 14–217) + right panel inline styles (lines 502–584)

---

### Task 1: Replace chat layout CSS selectors with `:has()` semantic targeting

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py:79-106`

**Rationale:** The current selectors use positional indices (`:first-child`, `:last-child`, `>`) across 4 DOM levels. Any Streamlit DOM change breaks the chain. `:has()` targets "the column that contains the chat input" — semantic, stable, and self-documenting.

- [ ] **Step 1: Replace lines 79–106 with `:has()`-based selectors**

Replace the block from line 79 to line 106:

```css
/* Our left column (chat): outer vertical block — flex fills column height */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"] {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

/* Messages container (nested stVerticalBlock from st.container): flex-grow, scrollable */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* Chat input wrapper: pushed to bottom by margin-top: auto */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child {
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
```

With:

```css
/* === Left Column: Chat === */
/* Target the column that contains the chat input — semantic, not positional */
[data-testid="stColumn"]:has([data-testid="stChatInput"]) > [data-testid="stVerticalBlock"] {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

/* Messages container (stVerticalBlock from st.container): flex-grow, scrollable */
[data-testid="stColumn"]:has([data-testid="stChatInput"]) > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* Chat input wrapper: pushed to bottom by margin-top: auto */
[data-testid="stColumn"]:has([data-testid="stChatInput"]) > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child {
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
```

Also remove the leftover comment line on line 79 (`/* Left column's outer vertical block: flex column, fills height (specific selector) */`) and the blank line 80.

- [ ] **Step 2: Verify the chat input CSS rule also exists**

Ensure `[data-testid="stChatInput"] { flex-shrink: 0; }` is still present (line 104–106, unchanged).

- [ ] **Step 3: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "fix: replace positional CSS selectors with :has() for chat layout"
```

---

### Task 2: Fix right panel vertical block overflow containment

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py:108-114` (right column CSS)

**Rationale:** The right column has `overflow-y: auto` but its direct child `stVerticalBlock` lacks `min-height: 0`. In a flex column, without `min-height: 0`, the child's intrinsic height can force the column to expand beyond `overflow-y: auto`'s clipping area, pushing overflow to the page level.

- [ ] **Step 1: Add `min-height: 0` to right column's vertical block**

Replace lines 108–114:

```css
/* === Right Column: Monitoring Panel === */
/* Our right column: last column in the nested horizontal block */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--card-border) transparent;
}
```

With:

```css
/* === Right Column: Monitoring Panel === */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--card-border) transparent;
}

/* Prevent vertical block from breaking overflow containment */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"] {
  min-height: 0;
}
```

- [ ] **Step 2: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "fix: add min-height:0 to right column vertical block for scroll containment"
```

---

### Task 3: Increase right panel label font sizes

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py:504,524,537,551,581` (inline styles)

**Rationale:** Current font-size is 13px (bumped from 10px in commit 4028df8). User feedback says labels are still too small. Bump to 15px for better readability while keeping the editorial proportions.

- [ ] **Step 1: Bump all 5 right panel labels from `font-size:13px` to `font-size:15px`**

Five changes — replace `font-size:13px` with `font-size:15px` in the following label `<span>` elements:

**Line 504 — Plan header (with steps):**
```python
# Old:
'<span style="font-size:13px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-weight:700">执行计划</span>'
# New:
'<span style="font-size:15px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-weight:700">执行计划</span>'
```

**Line 524 — Plan header (empty state):**
```python
# Old:
'<span style="font-size:13px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-family:Georgia,serif;font-weight:700">执行计划</span>'
# New:
'<span style="font-size:15px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-family:Georgia,serif;font-weight:700">执行计划</span>'
```

**Line 537 — Token header:**
```python
# Old:
'<span style="font-size:13px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-weight:700">Token</span>'
# New:
'<span style="font-size:15px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-weight:700">Token</span>'
```

**Line 551 — Screenshot header:**
```python
# Old:
'<span style="font-size:13px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-weight:700">实时截图</span>'
# New:
'<span style="font-size:15px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-weight:700">实时截图</span>'
```

**Line 581 — Replay header:**
```python
# Old:
'<span style="font-size:13px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-family:Georgia,serif;font-weight:700">操作回放</span>'
# New:
'<span style="font-size:15px;color:#a0988a;letter-spacing:2px;'
'text-transform:uppercase;font-family:Georgia,serif;font-weight:700">操作回放</span>'
```

- [ ] **Step 2: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "fix: increase right panel label font size from 13px to 15px"
```

---

### Task 4: Fix token card squeeze with min-height

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py:535-536` (token card container inline style)

**Rationale:** The token card in the right panel's plan+token row has minimal content in initial state (three zeros), causing the flex row to compress it. Adding `min-height: 100px` to the token card container prevents collapse.

- [ ] **Step 1: Add min-height to token card outer div**

At line 535, change:

```python
# Old:
token_html = (
    '<div style="font-family:Georgia,serif">'
# New:
token_html = (
    '<div style="font-family:Georgia,serif;min-height:100px">'
```

- [ ] **Step 2: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "fix: add min-height to token card to prevent squeeze"
```

---

### Task 5: Visual verification

**Files:**
- No code changes — visual inspection only

- [ ] **Step 1: Start the Streamlit frontend**

Run: `cd D:\AI_Agent_Demo && uv run streamlit run browsepilot/frontend/streamlit_app.py`

- [ ] **Step 2: Verify each fix**

| Check | Expected |
|-------|----------|
| First load — chat input position | At viewport bottom |
| Send message — input stays | Fixed at bottom |
| 10+ messages — scroll | Messages scroll internally, input fixed |
| Right panel — labels | 15px, bold, readable |
| Right panel — screenshot present | Scrolls within right panel, not whole page |
| Right panel — plan+token row | Token card not squeezed, min 100px height |
| No horizontal scrollbar | Page fits viewport width |

- [ ] **Step 3: If any issue found, inspect DOM**

Open browser DevTools (F12), inspect the element tree, verify:
- `[data-testid="stColumn"]:has([data-testid="stChatInput"])` matches the left column
- Left column's `> [data-testid="stVerticalBlock"]` has `flex: 1` applied
- Right column's `> [data-testid="stVerticalBlock"]` has `min-height: 0` applied
- Right column itself has `overflow-y: auto` applied

Adjust selectors if Streamlit version generates different DOM structure.

- [ ] **Step 4: Commit any adjustments if needed**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "fix: adjust CSS selectors after DOM verification"
```

---

## Verification Checklist

After all tasks:

- [ ] Chat input fixed at viewport bottom on first load
- [ ] Chat messages scroll internally, input stays pinned
- [ ] Right panel labels readable (15px bold)
- [ ] Screenshot scrolls within right panel
- [ ] Token card not squeezed in initial state
- [ ] Plan card + Token card visible side by side in right panel
- [ ] Replay section accessible via right panel scroll
- [ ] Sidebar functional
- [ ] No page-level horizontal scrollbar
- [ ] No page-level vertical scrollbar (internal scrolling only)
