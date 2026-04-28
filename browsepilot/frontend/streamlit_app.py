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

/* Page background */
.stApp, section.main, .main .block-container {
  background-color: var(--bg);
}

/* Typography */
.stApp, .stMarkdown, .stChatMessage, .stChatInput, .stSelectbox {
  font-family: Georgia, 'Times New Roman', serif;
}

/* Column divider */
[data-testid="column"] + [data-testid="column"] {
  border-left: 1px solid var(--border);
}

/* Card styling */
.stContainer, [data-testid="stVerticalBlock"] {
  border: 1px solid var(--card-border);
  border-radius: 0;
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

# ---- Sidebar ----
st.sidebar.title("BrowsePilot")
st.sidebar.markdown("具备深度规划与自省能力的浏览器自动化 AI 助手")
api_url = st.sidebar.text_input("Backend API URL", value="http://localhost:8000")
st.sidebar.markdown("---")
st.sidebar.caption("输入自然语言指令，Agent 自主操控浏览器完成任务")

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

# ---- Layout ----
left_col, right_col = st.columns([7, 3])

# ===== LEFT PANEL: Chat =====
with left_col:
    st.subheader("对话")

    # Render chat history (rendered on each rerun)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    task = st.chat_input("输入你的浏览器操作指令，例如：打开百度搜索 LangChain MCP...")

    if task:
        # Add user message immediately
        st.session_state.messages.append({"role": "user", "content": task})
        st.session_state.plan_steps = []

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

                        if event_type == "plan_generated":
                            steps = event["data"].get("steps", [])
                            st.session_state.plan_steps = steps
                            st.session_state.current_step = steps[0] if steps else ""
                            progress_placeholder.info(f"📋 已生成 {len(steps)} 步执行计划...")

                        elif event_type == "step_start":
                            step = event["data"].get("step", "")
                            st.session_state.current_step = step
                            progress_placeholder.info(f"🔄 {step}")

                        elif event_type == "screenshot":
                            b64 = event["data"].get("base64", "")
                            if b64:
                                st.session_state.current_screenshot = b64

                        elif event_type == "step_end":
                            step_count += 1
                            result = event["data"].get("result", {})
                            if isinstance(result, dict) and result.get("status") == "error":
                                progress_placeholder.warning(f"⚠️ 步骤失败，正在重试...")
                            else:
                                progress_placeholder.info(f"✅ 已完成 {step_count} 个步骤...")

                        elif event_type == "reflection":
                            decision = event["data"].get("decision", "")
                            if decision == "replan":
                                progress_placeholder.warning("🔄 正在重新规划...")

                        elif event_type == "token_update":
                            prompt = event["data"].get("prompt", 0)
                            completion = event["data"].get("completion", 0)
                            st.session_state.token_count = prompt + completion

                        elif event_type == "final_answer":
                            answer_content = event["data"].get("content", "")
                            total = event["data"].get("total_tokens", 0)
                            st.session_state.token_count = total
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
    st.subheader("监控面板")

    # Plan display
    if st.session_state.plan_steps:
        with st.expander("执行计划", expanded=True):
            for i, s in enumerate(st.session_state.plan_steps):
                if i == 0 and st.session_state.current_step:
                    st.markdown(f"**🔵 {s}**")
                else:
                    st.caption(f"{i+1}. {s}")

    # Current step
    if st.session_state.current_step:
        st.info(f"当前: {st.session_state.current_step}")

    # Live screenshot
    if st.session_state.current_screenshot:
        try:
            img_data = base64.b64decode(st.session_state.current_screenshot)
            st.image(BytesIO(img_data), caption="实时截图", use_container_width=True)
        except Exception:
            st.caption("(截图加载失败)")

    # Token counter
    st.metric("Token 消耗", st.session_state.token_count)

    # Replay section
    st.divider()
    st.subheader("操作回放")
    try:
        sessions_resp = requests.get(f"{api_url}/sessions", timeout=5)
        if sessions_resp.ok:
            sessions = sessions_resp.json()
            if sessions:
                selected = st.selectbox("选择历史会话", sessions)
                if selected and st.button("查看回放"):
                    replay_resp = requests.get(f"{api_url}/replay/{selected}", timeout=5)
                    if replay_resp.ok:
                        steps = replay_resp.json()
                        for s in steps:
                            st.caption(f"Step {s['step_index']}: {s['step']}")
                            if s.get("screenshot_path"):
                                try:
                                    with open(s["screenshot_path"], "rb") as f:
                                        st.image(f.read(), caption=s["step"], use_container_width=True)
                                except FileNotFoundError:
                                    st.caption("(截图文件不存在)")
            else:
                st.caption("暂无历史会话")
    except requests.exceptions.ConnectionError:
        st.caption("后端未连接")
