# BrowsePilot Frontend Plan B Layout Fix — Design Spec

> **Goal:** Fix chat scrolling + input positioning, right panel font sizes, screenshot scroll, and token card squeeze, using minimal CSS to complement Streamlit native chat components.

**Tech Stack:** Streamlit 1.35+, minimal CSS injection

**Approach:** Remove complex CSS selector chains that fight Streamlit DOM. Retain only three-layer flex constraints for viewport locking. Let `st.chat_message` and `st.chat_input` handle their own layout. Right panel fixes are inline style tweaks and targeted overflow constraints.

---

## 1. Chat Area — Fixed Bottom Input + Internal Scroll

### Problem

CSS selectors with 4+ nesting levels (`[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child > ...`) break when Streamlit DOM structure changes. The flex chain fails and the chat input drifts to the page top.

### Design

Keep only essential flex constraints:

1. **Viewport lock:** `html, body, [data-testid="stApp"]` → `height: 100vh; overflow: hidden`
2. **Main container fills viewport:** `[data-testid="stMain"] > [data-testid="stMainBlockContainer"]` → `flex column, height: 100%`
3. **Layout wrapper flex-fills:** `[data-testid="stLayoutWrapper"]` → `flex: 1; min-height: 0`
4. **Horizontal block fills wrapper:** `[data-testid="stLayoutWrapper"] [data-testid="stHorizontalBlock"]` → `flex: 1; min-height: 0`
5. **Columns are flex columns:** `[data-testid="stColumn"]` → `display: flex; flex-direction: column; overflow: hidden`
6. **Left column vertical block fills + scrolls:** selector targeting the chat column's outer vertical block → `flex: 1; overflow-y: auto; min-height: 0`
7. **Chat input sticks to bottom:** via `flex-shrink: 0; margin-top: auto` on the element container wrapping `stChatInput`

Remove: all `:first-child`/`:last-child`/`>` deep nesting selectors for the chat column. Replace with simpler selectors based on `st.chat_message` container structure.

### CSS scope

- Viewport lock: ~10 lines
- Flex layout: ~20 lines  
- Remove existing ~40 lines of complex selectors
- Keep existing typography, card, color, animation CSS (unchanged)

---

## 2. Right Panel — Font Sizes

### Problem

Four section labels ("执行计划", "Token", "实时截图", "操作回放") use `font-size:10px`, too small to read.

### Design

Change inline `font-size:10px` to `font-size:13px` and add `font-weight:700` for all four labels plus the empty state placeholder. These are pure inline style string replacements in Python code, no CSS class changes needed.

The `.phase-label` CSS class (10px) is kept for chat-thinking indicators inside the message area — those should stay small.

### Affected locations (streamlit_app.py)

- Plan header (~line 504)
- Plan empty state (~line 524)
- Token header (~line 538)
- Screenshot header (~line 551)
- Replay header (~line 581)

---

## 3. Right Panel — Screenshot Overflow Scroll

### Problem

Screenshot image overflows the right column and pushes content into page-level overflow. The `overflow-y: auto` on the right column doesn't work because a flex child has no `min-height: 0`.

### Design

Ensure the right column's outer vertical block has `min-height: 0` so `overflow-y: auto` on the column takes effect. The column CSS selector already has `overflow: hidden` for all columns; the right column override uses `overflow-y: auto`.

The fix is to verify the vertical block inside the right column also gets `min-height: 0` via a simple selector.

---

## 4. Right Panel — Token Card Squeeze

### Problem

In empty/initial state, the token card has little content (just three small numbers) and gets compressed by the adjacent plan card in the flex row.

### Design

Give the token card's container a `min-height: 100px` via inline style. This prevents the squeeze in empty state. The `flex: none` already on nested horizontal blocks prevents it from growing unexpectedly.

---

## 5. What Gets Changed

### streamlit_app.py CSS block

- **Remove:** Complex nested selectors for chat column (lines ~80-106 in current file: the `:first-child`, `:last-child`, nested `stVerticalBlock` selectors)
- **Keep:** Viewport lock (lines ~29-56), color tokens, typography, card styling, animations, scrollbar styling
- **Add:** Simplified left-column flex+scroll selector, chat input bottom-pin selector

### streamlit_app.py right panel section

- **Modify:** 5 inline style strings — font-size 10px → 13px + font-weight 700
- **Modify:** Token card container — add min-height inline style

---

## 6. What Stays Unchanged

- All Swiss Editorial design tokens (colors, fonts, borders)
- Sidebar implementation
- SSE event handling and `processing` state management
- `_phase_html()` and `_progress_bar_html()` helpers
- Plan card step rendering logic
- Replay section (session selector, screenshot display)
- Chat message rendering loop
