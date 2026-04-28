# BrowsePilot Frontend Redesign — Design Spec

> **Goal:** Redesign the Streamlit frontend with a dual-column layout (chat + monitoring panel) using Swiss Editorial visual style.

**Tech Stack:** Streamlit (Python), minimal custom CSS injection via `st.markdown(unsafe_allow_html=True)`

**Design Direction:** Swiss Editorial — magazine-grade typography, restrained color palette, generous whitespace. Like flipping through a meticulously designed aviation manual.

---

## 1. Overall Layout

Dual-column: chat area (left, flex: ~65%) + monitoring panel (right, fixed ~300px).

### Implementation approach

Streamlit doesn't natively support side-by-side columns with fixed ratios well. Use `st.columns([7, 3])` for the top-level split. The monitoring panel gets the narrower column.

```
+-------------------------+---------------+
| Chat Area               | Monitoring    |
| - Messages              | - Plan+Token  |
| - Thinking states       | - Screenshot   |
| - Input at bottom       | - Replay       |
+-------------------------+---------------+
```

### Breakpoints
- Not needed — Streamlit is desktop-only by default.

---

## 2. Monitoring Panel Internal Layout

Vertical stack within the right column, ordered top to bottom:

1. **Row 1 (fixed height):** Plan card (left, flex:1) + Token card (right, narrower)
2. **Row 2 (flex fill):** Screenshot card — absorbs all remaining vertical space
3. **Row 3 (fixed height):** Replay card — session selector dropdown

### Plan card
- Header: "执行计划" label + "3/5" progress fraction (large serif number)
- Body: step list — completed steps struck through in muted color, current step highlighted in vermillion with left border accent, upcoming steps in muted body color

### Token card
- Header: "Token" label
- Body: three rows — input (large bold number), output (large bold number), total (vermillion, separated by hairline rule)

### Screenshot card
- Header: "实时截图" label + red pulsing dot (live indicator)
- Body: placeholder area that fills flex space, dashed border when empty, replaced by image when screenshot available

### Replay card
- Header: "操作回放" label
- Body: Streamlit selectbox for session picker

---

## 3. Chat Area

### Message bubbles
- User: solid dark (#1a1a1a) background, light text (#faf9f6), right-aligned
- Assistant: no background, just text, left-aligned

### Thinking/status indicators
Replace generic spinners with phase labels:

| Phase | Display | Visual treatment |
|-------|---------|-----------------|
| Planning | "正在思考" + step preview | Small-caps label, animated dot |
| Executing | "执行中 — 步骤 N/M" + description | Small-caps label, progress bar |
| Reflecting | "正在检查" | Small-caps label, animated dot |
| Replanning | "正在调整计划" | Small-caps label, animated dot |
| Answering | "生成回答" | Small-caps label |
| Done | Result summary | No indicator needed |
| Error | Error message | Vermillion accent |

### Progress bar (executing phase)
Thin horizontal bar composed of M segments (one per step):
- Completed steps: solid vermillion
- Current step: vermillion with pulse animation
- Pending steps: light warm gray

### Input area
- Bottom of chat column, fixed
- Label "指令输入" in small caps above
- Text input + "发送 →" action on the same line
- Underline separator between label and input row

---

## 4. Design Tokens

### Color palette

| Token | Hex | Usage |
|-------|-----|-------|
| Background | `#faf9f6` | Page background |
| Surface | `#fefdfb` | Card backgrounds |
| Border | `#d4cdc2` | Column dividers |
| Card border | `#e8e0d4` | Card borders |
| Text primary | `#1a1a1a` | Headlines, user bubbles |
| Text body | `#4a4238` | Assistant text, body |
| Text muted | `#8b7f6e` | Meta text, upcoming steps |
| Text disabled | `#c4b5a5` | Completed steps |
| Accent | `#e33e2b` | Vermillion — current step, progress, errors, live dot |
| User bubble bg | `#1a1a1a` | User message background |
| User bubble text | `#faf9f6` | User message text |
| Input underline | `#d4cdc2` | Bottom border of input area |

### Typography

| Role | Font | Size | Weight | Letter-spacing |
|------|------|------|--------|---------------|
| App title | Georgia, serif | 20px | 700 | -0.5px |
| Section labels (small caps) | Georgia, serif | 10px | 400 | 2px, uppercase |
| Body text | Georgia, serif | 14px | 400 | normal |
| Step list | Georgia, serif | 12px | 400 | normal |
| Progress fraction | Georgia, serif | 18px | 700 | normal |
| Token numbers | Georgia, serif | 14px | 700 | normal |
| Input text | Georgia, serif | 14px | 400 | normal |
| Code/technical | monospace | inherit | 400 | normal |

### Spacing scale

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Tight internal padding |
| sm | 8px | Card internal padding |
| md | 12px | Card gaps, panel spacing |
| lg | 16px | Column padding |
| xl | 20px | Chat area padding |

### Borders & dividers
- Column divider: `1px solid #d4cdc2`
- Card border: `1px solid #e8e0d4`
- Hairline rule (inside cards): `1px solid #e8e0d4`
- Section underline: `1px solid #d4cdc2`
- No border-radius on cards (editorial sharpness)

### Animations

| Element | Animation | Duration |
|---------|-----------|----------|
| Live indicator dot | `fadeInOut` pulse | 1.5s ease-in-out infinite |
| Thinking dot | `fadeInOut` pulse | 1s ease-in-out infinite |
| Progress bar active segment | `fadeInOut` pulse | 1s ease-in-out infinite |
| Current step left border | Static (no animation needed) | — |

```css
@keyframes fadeInOut {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}
```

---

## 5. Component States

### Chat message: thinking/planning
```
[label: 正在思考] (10px, small caps, muted color)
Body text describing what's being thought about
[animated dot: 4px, vermillion, pulse]
[step preview list]
```

### Chat message: executing
```
[label: 执行中 — 步骤 3/5] (10px, small caps, muted)
Current action description
[progress bar: 5 segments, 3 full + 1 pulsing + 1 empty]
```

### Chat message: complete
```
[label: 完成] (10px, small caps, muted)
Result summary in body text
```

### Chat message: error
```
[label: 错误] (10px, small caps, vermillion)
Error description in body text
```

### Plan card: step states
- Completed: `text-decoration: line-through`, color `#c4b5a5`
- Current: color `#e33e2b`, `font-weight: 600`, `font-style: italic`, `border-left: 2px solid #e33e2b`
- Pending: color `#8b7f6e`

### Screenshot card: live indicator
- Red dot (5px, `#e33e2b`, `border-radius: 50%`) with `fadeInOut` animation
- Appears when agent is executing

---

## 6. What Gets Removed

- Left sidebar with project description text
- Default Streamlit "running" spinner in chat
- Generic blue/purple Streamlit default theme

---

## 7. CSS Injection Strategy

Streamlit allows CSS injection via:
```python
st.markdown("""
<style>
/* Custom CSS here */
</style>
""", unsafe_allow_html=True)
```

Minimal CSS needed:
1. Font family override (Georgia throughout)
2. Color overrides for Streamlit containers
3. Animation keyframes
4. Card styling (.stContainer overrides)
5. Column gap control

Keep CSS lean — rely on Streamlit's native layout where possible, override only where needed for the editorial aesthetic.

---

## 8. File to Modify

- `browsepilot/frontend/streamlit_app.py` — complete layout rewrite

No new files needed. All design achieved through Streamlit layout primitives + minimal CSS injection.
