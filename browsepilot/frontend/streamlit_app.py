"""BrowsePilot Streamlit frontend — chat + monitoring panel."""

import json
import base64
from io import BytesIO

import streamlit as st
import requests


st.set_page_config(page_title="BrowsePilot", layout="wide")

# ---- CSS Injection ----
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
  background-color: var(--bg);
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

/* Column divider */
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
  scrollbar-width: thin;
  scrollbar-color: var(--card-border) transparent;
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

st.markdown(CSS, unsafe_allow_html=True)

# ---- Sidebar ----
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

# ---- Session State ----
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_screenshot" not in st.session_state:
    st.session_state.current_screenshot = None
if "current_step" not in st.session_state:
    st.session_state.current_step = ""
if "token_count" not in st.session_state:
    st.session_state.token_count = 0
if "plan_steps" not in st.session_state:
    st.session_state.plan_steps = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "thinking_phase" not in st.session_state:
    st.session_state.thinking_phase = None  # None | "planning" | "executing" | "reflecting" | "replanning" | "answering"
if "thinking_message" not in st.session_state:
    st.session_state.thinking_message = ""
if "current_step_index" not in st.session_state:
    st.session_state.current_step_index = 0
if "total_steps" not in st.session_state:
    st.session_state.total_steps = 0
if "prompt_tokens" not in st.session_state:
    st.session_state.prompt_tokens = 0
if "completion_tokens" not in st.session_state:
    st.session_state.completion_tokens = 0

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

# ---- Layout ----
left_col, right_col = st.columns([7, 3])

# ===== LEFT PANEL: Chat =====
with left_col:
    # Render chat history (rendered on each rerun)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    task = st.chat_input("输入你的浏览器操作指令，例如：打开百度搜索 LangChain MCP...")

    if task:
        # Add user message immediately
        st.session_state.messages.append({"role": "user", "content": task})
        # Reset all task-specific state for the new task
        st.session_state.plan_steps = []
        st.session_state.current_step = ""
        st.session_state.current_screenshot = None
        st.session_state.token_count = 0
        st.session_state.prompt_tokens = 0
        st.session_state.completion_tokens = 0
        st.session_state.thinking_phase = None
        st.session_state.thinking_message = ""
        st.session_state.current_step_index = 0
        st.session_state.total_steps = 0

        # Show assistant bubble with real-time progress
        with st.chat_message("assistant"):
            progress_placeholder = st.empty()

            try:
                resp = requests.post(
                    f"{api_url}/chat/stream",
                    json={"task": task},
                    stream=True,
                    timeout=120,
                )

                answer_content = ""
                step_count = 0

                # Buffer for collecting SSE data chunks
                buffer = ""
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                    if not chunk:
                        continue
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        lines = event_str.strip().split("\n")
                        data_line = ""
                        for line in lines:
                            if line.startswith("data: "):
                                data_line = line[6:]
                                break
                        if not data_line:
                            continue
                        try:
                            event = json.loads(data_line)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("event")

                        if event_type == "thinking_status":
                            phase = event["data"].get("phase", "")
                            message = event["data"].get("message", "")
                            step_index = event["data"].get("step_index", 0)
                            total_steps = event["data"].get("total_steps", 0)
                            st.session_state.thinking_phase = phase
                            st.session_state.thinking_message = message
                            if step_index:
                                st.session_state.current_step_index = step_index
                            if total_steps:
                                st.session_state.total_steps = total_steps
                            # Render phase indicator for non-executing phases (executing handled by step_start/step_end)
                            if phase in ("planning", "reflecting", "replanning", "answering"):
                                progress_placeholder.markdown(
                                    _phase_html(phase, message),
                                    unsafe_allow_html=True,
                                )

                        elif event_type == "plan_generated":
                            steps = event["data"].get("steps", [])
                            st.session_state.plan_steps = steps
                            st.session_state.current_step = steps[0] if steps else ""
                            st.session_state.total_steps = len(steps)
                            st.session_state.thinking_phase = "executing"
                            progress_placeholder.markdown(
                                _phase_html("planning", f"已制定 {len(steps)} 步执行计划") + _progress_bar_html(0, len(steps)),
                                unsafe_allow_html=True,
                            )

                        elif event_type == "step_start":
                            step = event["data"].get("step", "")
                            st.session_state.current_step = step
                            if step_index := event["data"].get("step_index"):
                                st.session_state.current_step_index = step_index + 1  # 0-based to 1-based
                            idx = st.session_state.current_step_index
                            total = st.session_state.total_steps
                            progress_placeholder.markdown(
                                _phase_html("executing", step, idx, total) + _progress_bar_html(idx, total),
                                unsafe_allow_html=True,
                            )

                        elif event_type == "screenshot":
                            b64 = event["data"].get("base64", "")
                            if b64:
                                st.session_state.current_screenshot = b64

                        elif event_type == "step_end":
                            result = event["data"].get("result", {})
                            if isinstance(result, dict) and result.get("status") == "error":
                                progress_placeholder.markdown(
                                    f'<div class="phase-label" style="color:#e33e2b">重试中<span class="thinking-dot"></span></div>'
                                    f'<div style="font-family:Georgia,serif;color:#e33e2b;font-size:14px">⚠️ 步骤失败，正在重试...</div>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                step_count += 1
                                progress_placeholder.markdown(
                                    _phase_html("executing", f"已完成 {step_count} 个步骤", step_count, len(st.session_state.plan_steps))
                                    + _progress_bar_html(step_count + 1, len(st.session_state.plan_steps)),
                                    unsafe_allow_html=True,
                                )

                        elif event_type == "reflection":
                            decision = event["data"].get("decision", "")
                            if decision == "replan":
                                progress_placeholder.markdown(
                                    _phase_html("replanning", "调整执行策略..."),
                                    unsafe_allow_html=True,
                                )

                        elif event_type == "replan":
                            new_steps = event["data"].get("new_steps", [])
                            if new_steps:
                                st.session_state.plan_steps = new_steps
                                st.session_state.total_steps = len(new_steps)
                                st.session_state.current_step_index = 0

                        elif event_type == "token_update":
                            prompt = event["data"].get("prompt", 0)
                            completion = event["data"].get("completion", 0)
                            st.session_state.prompt_tokens = prompt
                            st.session_state.completion_tokens = completion
                            st.session_state.token_count = prompt + completion

                        elif event_type == "final_answer":
                            answer_content = event["data"].get("content", "")
                            total = event["data"].get("total_tokens", 0)
                            st.session_state.token_count = total
                            st.session_state.prompt_tokens = 0
                            st.session_state.completion_tokens = 0
                            st.session_state.thinking_phase = None
                            progress_placeholder.empty()
                            st.write(answer_content)
                            st.session_state.messages.append({"role": "assistant", "content": answer_content})

                        elif event_type == "error":
                            error_msg = event["data"].get("message", "Unknown error")
                            progress_placeholder.empty()
                            st.error(f"❌ 错误: {error_msg}")
                            answer_content = f"❌ 错误: {error_msg}"

                # If no final_answer received, show warning
                if not answer_content:
                    progress_placeholder.warning("任务执行完成，但未获取到回答内容")

            except requests.exceptions.ConnectionError:
                st.error(f"无法连接到后端 {api_url}，请确认后端已启动")
            except Exception as e:
                st.error(f"请求失败: {str(e)}")


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
            st.image(BytesIO(img_data), width="stretch")
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
                                            width="stretch",
                                        )
                                except FileNotFoundError:
                                    st.caption("(截图文件不存在)")
            else:
                st.caption("暂无历史会话")
    except requests.exceptions.ConnectionError:
        st.caption("后端未连接")
