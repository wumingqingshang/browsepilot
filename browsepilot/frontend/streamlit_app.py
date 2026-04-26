"""BrowsePilot Streamlit frontend — chat + monitoring panel."""

import json
import base64
from io import BytesIO

import streamlit as st
import requests


st.set_page_config(page_title="BrowsePilot", layout="wide")

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

    # Render chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    task = st.chat_input("输入你的浏览器操作指令，例如：打开百度搜索 LangChain MCP...")

    if task:
        # Add user message
        st.session_state.messages.append({"role": "user", "content": task})
        st.session_state.plan_steps = []

        try:
            resp = requests.post(
                f"{api_url}/chat/stream",
                json={"task": task},
                stream=True,
                timeout=120,
            )

            answer_text = ""

            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("event")

                if event_type == "plan_generated":
                    steps = event["data"].get("steps", [])
                    st.session_state.plan_steps = steps
                    st.session_state.current_step = steps[0] if steps else ""

                elif event_type == "step_start":
                    step = event["data"].get("step", "")
                    st.session_state.current_step = step

                elif event_type == "screenshot":
                    b64 = event["data"].get("base64", "")
                    if b64:
                        st.session_state.current_screenshot = b64

                elif event_type == "step_end":
                    pass  # Handled by screenshot display

                elif event_type == "reflection":
                    pass  # Status shown in monitoring panel

                elif event_type == "token_update":
                    prompt = event["data"].get("prompt", 0)
                    completion = event["data"].get("completion", 0)
                    st.session_state.token_count = prompt + completion

                elif event_type == "final_answer":
                    content = event["data"].get("content", "")
                    total = event["data"].get("total_tokens", 0)
                    answer_text = content
                    st.session_state.messages.append({"role": "assistant", "content": content})
                    st.session_state.token_count = total

                elif event_type == "error":
                    error_msg = event["data"].get("message", "Unknown error")
                    st.session_state.messages.append({"role": "assistant", "content": f"❌ 错误: {error_msg}"})

            # Rerun to refresh chat display
            if answer_text:
                st.rerun()

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
