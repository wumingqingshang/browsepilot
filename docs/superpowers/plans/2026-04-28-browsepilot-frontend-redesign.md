# BrowsePilot Frontend Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Streamlit frontend with dual-column layout, Swiss Editorial visual style, and phase-based thinking status indicators.

**Architecture:** Single-file Streamlit app (`streamlit_app.py`). Layout uses `st.columns([7, 3])` for chat/monitoring split, nested columns for plan+token row. CSS injected via `st.markdown(unsafe_allow_html=True)` for typography and color overrides. Phase-based status indicators replace generic spinners using the `thinking_status` SSE events (already emitted by backend).

**Tech Stack:** Streamlit (Python), CSS injection via `st.markdown(unsafe_allow_html=True)`, Georgia web-safe serif font

**Testing approach:** Streamlit has no official unit-test framework for UI. Verification is visual — run the app with `streamlit run`, exercise all states (idle, planning, executing, done, error), confirm visual output matches spec. Helper functions (CSS string generation, phase label lookup) are tested inline.

---

## File Map

| File | Role |
|------|------|
| `browsepilot/frontend/streamlit_app.py` | **MODIFY** — Complete layout and styling rewrite (~200 → ~280 lines) |

No new files. No backend changes needed (thinking_status events already emitted).

---

### Task 1: CSS Foundation

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py` (insert after `st.set_page_config`)

Inject Swiss Editorial design tokens as a CSS string constant, then apply via `st.markdown`.

- [ ] **Step 1: Add CSS constant and injection**

Add this block immediately after `st.set_page_config(page_title="BrowsePilot", layout="wide")`:

```python
# ---- CSS Injection ----
CSS = """
<style>
/* === Swiss Editorial Design Tokens === */
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,600&display=swap');

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

/* Page background */
.stApp, section.main, .main .block-container {
  background-color: var(--bg);
}

/* Typography */
.stApp, .stMarkdown, .stChatMessage, .stChatInput, .stSelectbox, p, span, div {
  font-family: Georgia, 'Times New Roman', serif !important;
}

/* Column divider */
[data-testid="column"] + [data-testid="column"] {
  border-left: 1px solid var(--border);
}

/* Card styling */
.stContainer, [data-testid="stVerticalBlock"] {
  border: 1px solid var(--card-border);
  background: var(--surface);
}

/* Chat messages */
[data-testid="stChatMessage"] {
  background: transparent !important;
}

/* Input underline */
[data-testid="stChatInput"] {
  border-top: 1px solid var(--border);
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

/* Sidebar cleanup — hide default sidebar nav */
[data-testid="stSidebarNav"] { display: none; }

/* Animations */
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
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)
```

- [ ] **Step 2: Verify CSS applies**

Run: `streamlit run browsepilot/frontend/streamlit_app.py`
Expected: App loads with warm off-white background, Georgia font. No Streamlit default blue/purple visible.

- [ ] **Step 3: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "style: inject Swiss Editorial CSS foundation"
```

---

### Task 2: Sidebar Cleanup

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py` (lines 13-18, the sidebar block)

Replace the verbose sidebar with a minimal version — keep API URL, remove description text.

- [ ] **Step 1: Replace sidebar content**

Replace:
```python
st.sidebar.title("BrowsePilot")
st.sidebar.markdown("具备深度规划与自省能力的浏览器自动化 AI 助手")
api_url = st.sidebar.text_input("Backend API URL", value="http://localhost:8000")
st.sidebar.markdown("---")
st.sidebar.caption("输入自然语言指令，Agent 自主操控浏览器完成任务")
```

With:
```python
with st.sidebar:
    st.markdown(
        '<span style="font-family:Georgia,serif;font-size:20px;font-weight:700;'
        'color:#1a1a1a;letter-spacing:-0.5px">BrowsePilot</span>',
        unsafe_allow_html=True,
    )
    st.caption("浏览器自动化 AI 助手")
    st.markdown("---")
    api_url = st.text_input("Backend API URL", value="http://localhost:8000", label_visibility="collapsed")
    st.markdown("---")
    if st.session_state.get("session_id"):
        st.caption(f"Session #{st.session_state.session_id}")
```

- [ ] **Step 2: Add session_id to session state init**

In the session state init block, add after the existing keys:
```python
if "session_id" not in st.session_state:
    st.session_state.session_id = None
```

- [ ] **Step 3: Verify**

Run: `streamlit run browsepilot/frontend/streamlit_app.py`
Expected: Sidebar shows only app name, subtitle, API URL, and session ID (when available). No long description text.

- [ ] **Step 4: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "refactor: clean sidebar to Swiss Editorial minimal style"
```

---

### Task 3: Add thinking_status Event Handling

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py` (inside the SSE event loop)

Add handler for `thinking_status` events, and add state tracking variables for the current thinking phase.

- [ ] **Step 1: Add thinking state to session state init**

Add after existing session state keys:
```python
if "thinking_phase" not in st.session_state:
    st.session_state.thinking_phase = None  # None | "planning" | "executing" | "reflecting" | "replanning" | "answering"
if "thinking_message" not in st.session_state:
    st.session_state.thinking_message = ""
if "current_step_index" not in st.session_state:
    st.session_state.current_step_index = 0
if "total_steps" not in st.session_state:
    st.session_state.total_steps = 0
```

- [ ] **Step 2: Add thinking_status handler in SSE event loop**

In the SSE event loop, add before the `if event_type == "plan_generated"` block:

```python
if event_type == "thinking_status":
    phase = event["data"].get("phase", "")
    message = event["data"].get("message", "")
    step_index = event["data"].get("step_index", 0)
    total_steps = event["data"].get("total_steps", 0)
    st.session_state.thinking_phase = phase
    st.session_state.thinking_message = message
    st.session_state.current_step_index = step_index
    st.session_state.total_steps = total_steps or len(st.session_state.plan_steps)
```

- [ ] **Step 3: Update plan_generated handler to set total_steps**

Replace the existing `plan_generated` handler:
```python
elif event_type == "plan_generated":
    steps = event["data"].get("steps", [])
    st.session_state.plan_steps = steps
    st.session_state.current_step = steps[0] if steps else ""
    st.session_state.total_steps = len(steps)
    st.session_state.thinking_phase = "executing"
    progress_placeholder.markdown(
        _phase_html("plan_generated", f"已制定 {len(steps)} 步执行计划"),
        unsafe_allow_html=True,
    )
```

- [ ] **Step 4: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "feat: handle thinking_status SSE events for phase tracking"
```

---

### Task 4: Phase-based Status Display in Chat

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py` (the progress_placeholder rendering logic)

Replace generic `st.info`/`st.warning` calls with styled phase indicators matching the Swiss Editorial spec.

- [ ] **Step 1: Add phase HTML helper functions**

Add these helper functions before the main layout section (after session state init):

```python
# ---- Phase Display Helpers ----

PHASE_LABELS = {
    "planning": "正在思考",
    "executing": "执行中",
    "reflecting": "正在检查",
    "replanning": "正在调整计划",
    "answering": "生成回答",
}


def _phase_html(phase: str, message: str, step_index: int = 0, total_steps: int = 0) -> str:
    """Build the HTML for a phase status indicator."""
    label = PHASE_LABELS.get(phase, phase)
    if phase == "executing" and total_steps:
        label = f"执行中 — 步骤 {step_index}/{total_steps}"
    return (
        f'<div class="phase-label">{label}'
        f'<span class="thinking-dot"></span></div>'
        f'<div style="font-family:Georgia,serif;color:#4a4238;font-size:14px">{message}</div>'
    )


def _progress_bar_html(current: int, total: int) -> str:
    """Build HTML for the step progress bar (M segments)."""
    if not total:
        return ""
    segments = []
    for i in range(total):
        if i < current - 1:
            cls = "done"
        elif i == current - 1:
            cls = "active"
        else:
            cls = ""
        segments.append(f'<div class="progress-segment {cls}"></div>')
    return f'<div class="progress-bar">{"".join(segments)}</div>'
```

- [ ] **Step 2: Replace status display calls in SSE event loop**

Replace ALL the `progress_placeholder` calls in the event loop:

Replace `progress_placeholder.info(f"📋 已生成 {len(steps)} 步执行计划...")` (line 94) with:
```python
progress_placeholder.markdown(
    _phase_html("planning", f"已制定 {len(steps)} 步执行计划") + _progress_bar_html(0, len(steps)),
    unsafe_allow_html=True,
)
```

Replace `progress_placeholder.info(f"🔄 {step}")` (line 99) with:
```python
idx = st.session_state.current_step_index
total = st.session_state.total_steps
progress_placeholder.markdown(
    _phase_html("executing", step, idx, total) + _progress_bar_html(idx, total),
    unsafe_allow_html=True,
)
```

Replace `progress_placeholder.info(f"✅ 已完成 {step_count} 个步骤...")` (line 112) with:
```python
progress_placeholder.markdown(
    _phase_html("executing", f"已完成 {step_count} 个步骤", step_count, len(st.session_state.plan_steps))
    + _progress_bar_html(step_count, len(st.session_state.plan_steps)),
    unsafe_allow_html=True,
)
```

Replace `progress_placeholder.warning(f"⚠️ 步骤失败，正在重试...")` (line 110) with:
```python
progress_placeholder.markdown(
    f'<div class="phase-label" style="color:#e33e2b">重试中<span class="thinking-dot"></span></div>'
    f'<div style="font-family:Georgia,serif;color:#e33e2b;font-size:14px">⚠️ 步骤失败，正在重试...</div>',
    unsafe_allow_html=True,
)
```

Replace `progress_placeholder.warning("🔄 正在重新规划...")` (line 117) with:
```python
progress_placeholder.markdown(
    _phase_html("replanning", "调整执行策略..."),
    unsafe_allow_html=True,
)
```

- [ ] **Step 3: Verify states visually**

Run: `streamlit run browsepilot/frontend/streamlit_app.py`
Submit a task, observe: planning phase shows "正在思考" label + pulsing dot, executing shows "执行中 — 步骤 N/M" + progress bar, done shows result. No blue/purple Streamlit spinners.

- [ ] **Step 4: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "feat: replace generic spinners with Swiss Editorial phase indicators and progress bar"
```

---

### Task 5: Monitoring Panel Restructure

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py` (lines 148-200, the right panel block)

Replace the entire right panel with the new structure: Plan+Token row, Screenshot card, Replay card. Use nested `st.columns` for the row layout.

- [ ] **Step 1: Replace the entire right panel block**

Replace lines 148-200 (from `# ===== RIGHT PANEL: Monitoring =====` to end) with:

```python
# ===== RIGHT PANEL: Monitoring =====
with right_col:
    # ---- Row 1: Plan + Token ----
    plan_col, token_col = st.columns([3, 1])
    with plan_col:
        if st.session_state.plan_steps:
            total = len(st.session_state.plan_steps)
            current = st.session_state.current_step_index
            steps_html = '<div style="font-family:Georgia,serif">'
            steps_html += (
                '<span style="font-size:10px;color:#a0988a;letter-spacing:2px;'
                'text-transform:uppercase">执行计划</span>'
            )
            steps_html += (
                f'<span style="float:right;font-family:Georgia,serif;font-size:18px;'
                f'font-weight:700;color:#e33e2b;line-height:1">{current}'
                f'<span style="font-size:10px;color:#a0988a">/{total}</span></span>'
            )
            for i, s in enumerate(st.session_state.plan_steps):
                if i < current - 1:
                    cls = "done"
                elif i == current - 1:
                    cls = "current"
                else:
                    cls = "pending"
                steps_html += f'<div class="plan-step {cls}">{i+1}. {s}</div>'
            steps_html += '</div>'
            st.markdown(steps_html, unsafe_allow_html=True)
        else:
            st.markdown(
                '<span style="font-size:10px;color:#a0988a;letter-spacing:2px;'
                'text-transform:uppercase;font-family:Georgia,serif">执行计划</span>'
                '<div style="color:#c4b5a5;font-size:12px;font-family:Georgia,serif;'
                'font-style:italic;margin-top:8px">等待任务...</div>',
                unsafe_allow_html=True,
            )

    with token_col:
        prompt_tokens = st.session_state.get("prompt_tokens", 0)
        completion_tokens = st.session_state.get("completion_tokens", 0)
        total_tokens = st.session_state.token_count or (prompt_tokens + completion_tokens)
        token_html = (
            '<div style="font-family:Georgia,serif">'
            '<span style="font-size:10px;color:#a0988a;letter-spacing:2px;'
            'text-transform:uppercase">Token</span>'
            '<div style="font-size:11px;line-height:2.2;color:#8b7f6e;margin-top:8px">'
            f'输入 <b style="color:#1a1a1a;font-size:14px">{prompt_tokens:,}</b><br>'
            f'输出 <b style="color:#1a1a1a;font-size:14px">{completion_tokens:,}</b><br>'
            '<div style="border-top:1px solid #e8e0d4;margin-top:4px;padding-top:4px">'
            f'总计 <b style="color:#e33e2b;font-size:14px">{total_tokens:,}</b>'
            '</div></div></div>'
        )
        st.markdown(token_html, unsafe_allow_html=True)

    # ---- Row 2: Screenshot ----
    screenshot_html = (
        '<div style="font-family:Georgia,serif;margin-top:4px">'
        '<span style="font-size:10px;color:#a0988a;letter-spacing:2px;'
        'text-transform:uppercase">实时截图</span>'
    )
    if st.session_state.thinking_phase == "executing":
        screenshot_html += '<span class="live-dot" style="margin-left:6px"></span>'
    screenshot_html += '</div>'
    st.markdown(screenshot_html, unsafe_allow_html=True)

    if st.session_state.current_screenshot:
        try:
            img_data = base64.b64decode(st.session_state.current_screenshot)
            st.image(BytesIO(img_data), use_container_width=True)
        except Exception:
            st.markdown(
                '<div style="border:1px dashed #e8e0d4;padding:20px;text-align:center;'
                'color:#c4b5a5;font-family:Georgia,serif;font-style:italic;font-size:12px">'
                '截图加载失败</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="border:1px dashed #e8e0d4;padding:20px;text-align:center;'
            'color:#c4b5a5;font-family:Georgia,serif;font-style:italic;font-size:12px">'
            '等待浏览器截图...</div>',
            unsafe_allow_html=True,
        )

    # ---- Row 3: Replay ----
    st.markdown("---")
    st.markdown(
        '<span style="font-size:10px;color:#a0988a;letter-spacing:2px;'
        'text-transform:uppercase;font-family:Georgia,serif">操作回放</span>',
        unsafe_allow_html=True,
    )
    try:
        sessions_resp = requests.get(f"{api_url}/sessions", timeout=5)
        if sessions_resp.ok:
            sessions = sessions_resp.json()
            if sessions:
                selected = st.selectbox(
                    "选择历史会话", sessions, label_visibility="collapsed"
                )
                if selected and st.button("查看回放"):
                    replay_resp = requests.get(
                        f"{api_url}/replay/{selected}", timeout=5
                    )
                    if replay_resp.ok:
                        steps = replay_resp.json()
                        for s in steps:
                            st.caption(f"Step {s['step_index']}: {s['step']}")
                            if s.get("screenshot_path"):
                                try:
                                    with open(s["screenshot_path"], "rb") as f:
                                        st.image(
                                            f.read(),
                                            caption=s["step"],
                                            use_container_width=True,
                                        )
                                except FileNotFoundError:
                                    st.caption("(截图文件不存在)")
            else:
                st.caption("暂无历史会话")
    except requests.exceptions.ConnectionError:
        st.caption("后端未连接")
```

- [ ] **Step 2: Add prompt_tokens and completion_tokens to session state init**

Add after existing keys:
```python
if "prompt_tokens" not in st.session_state:
    st.session_state.prompt_tokens = 0
if "completion_tokens" not in st.session_state:
    st.session_state.completion_tokens = 0
```

- [ ] **Step 3: Update token_update event handler to split prompt/completion**

Replace the existing `token_update` handler:
```python
elif event_type == "token_update":
    prompt = event["data"].get("prompt", 0)
    completion = event["data"].get("completion", 0)
    st.session_state.prompt_tokens = prompt
    st.session_state.completion_tokens = completion
    st.session_state.token_count = prompt + completion
```

- [ ] **Step 4: Remove subheader from left panel**

Replace:
```python
st.subheader("对话")
```
With nothing (remove the line entirely).

- [ ] **Step 5: Verify monitoring panel visually**

Run: `streamlit run browsepilot/frontend/streamlit_app.py`
Expected: Monitoring panel shows plan+token side by side. Plan has step states (struck-through done, red italic current, muted pending). Screenshot area shows dashed border placeholder when empty, live dot when executing.

- [ ] **Step 6: Commit**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "refactor: restructure monitoring panel with plan+token row, screenshot card, replay"
```

---

### Task 6: Final Verification and Polish

**Files:**
- Modify: `browsepilot/frontend/streamlit_app.py` (final cleanup)

Run full end-to-end verification, fix any visual issues.

- [ ] **Step 1: Test all phases**

Run the app and submit a task. Verify each phase renders correctly:
1. **Idle** (no task): Plan area shows "等待任务...", Screenshot shows dashed placeholder, Token shows zeros
2. **Planning**: Chat shows "正在思考" + dot, plan area updates when plan_generated arrives
3. **Executing**: Chat shows "执行中 — 步骤 N/M" + progress bar, monitoring shows current step highlighted, live dot on screenshot
4. **Step failure/retry**: Chat shows "重试中" in vermillion
5. **Replanning**: Chat shows "正在调整计划"
6. **Done**: Chat shows final answer (no phase indicator), monitoring shows all steps done, live dot hidden
7. **Error**: Chat shows error in vermillion, no progress bar

- [ ] **Step 2: Verify sidebar**

Check: No default Streamlit page nav visible (hidden by CSS). API URL input functional. Session ID shown when set.

- [ ] **Step 3: Fix visual issues**

Address any CSS specificity problems — Streamlit's own CSS may override some rules. Add `!important` where needed, or use higher-specificity selectors.

- [ ] **Step 4: Commit final polish**

```bash
git add browsepilot/frontend/streamlit_app.py
git commit -m "polish: verify all phase states, fix CSS edge cases"
```

---

## Self-Review Notes

1. **Spec coverage:** Every section in the spec maps to at least one task:
   - Overall layout → Task 5 (columns already exist)
   - Panel internal layout → Task 5
   - Chat area → Tasks 3, 4
   - Design tokens → Task 1 (CSS)
   - Component states → Tasks 3, 4, 5
   - Sidebar removal → Task 2
   - CSS injection → Task 1

2. **Placeholder scan:** No TBD/TODO. All code blocks are complete.

3. **Type consistency:** Phase strings match backend `thinking_status` event phase values: `planning`, `executing`, `reflecting`, `replanning`, `answering`.
