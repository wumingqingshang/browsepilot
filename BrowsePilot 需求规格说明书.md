# BrowsePilot 需求规格说明书  
**面向 AI 辅助编码 · 完整工程实现指引**

---

## 1. 项目概述

### 1.1 项目名称
**BrowsePilot** — 具备深度规划与自省能力的浏览器自动化 AI 个人助理

### 1.2 项目定位
一个**专门用于求职面试展示**的、**架构完整的**、**生产级雏形**的 AI Agent 应用。用户通过自然语言指令操控真实浏览器（基于 Playwright），Agent 自主完成网页搜索、信息提取、多步交互等任务，并内置操作审计、异常重试、成本追踪等工程化能力。

### 1.3 核心差异化能力
- **深度规划**：Agent 在执行前生成结构化执行计划，而非简单的 ReAct 单步推理。
- **自省与纠错**：工具调用失败时，Agent 能基于截图和错误信息重新规划，而非无脑重试。
- **全链路可观测**：每一步操作均有 JSON 日志 + 截图快照，支持事后回放。
- **标准 MCP 封装**：浏览器操作全部通过 MCP Server 暴露，工具可被任何 MCP 客户端复用。
- **零安装体验**：提供 Web 界面，面试官通过链接即可直接体验，无需本地配置。

---

## 2. 技术栈

| 层级 | 选型 | 版本要求 |
|------|------|-----------|
| **Agent 框架** | deepagent(langchain) | ≥0.5.0 |
| **LLM 接入** | langchain-openai / langchain-anthropic | 兼容 OpenAI/Anthropic 协议 |
| **浏览器自动化** | Playwright for Python | ≥1.40 |
| **MCP 协议实现** | mcp (Python SDK) | ≥1.25.0 |
| **后端 Web 框架** | FastAPI | ≥0.110 |
| **前端** | Streamlit | ≥1.35 |
| **日志与可观测性** | loguru, Prometheus client (可选) | - |
| **项目管理** | pyproject.toml + uv 包管理器 | - |

---

## 3. 系统架构
```text
┌─────────────────┐     HTTP/SSE      ┌──────────────────┐     MCP协议      ┌─────────────────┐
│  Streamlit FE   │ ◄───────────────► │  FastAPI 后端     │ ◄────────────► │  browser-mcp    │
│  (聊天+监控面板) │                   │  (Agent 服务)     │                │  (Playwright)   │
└─────────────────┘                   │  - /chat/stream   │                └─────────────────┘
                                      │  - /history/{id}  │
                                      │  - /replay/{id}   │
                                      └──────────────────┘
```
- **Streamlit 前端**：展示对话、实时截图流、Token 仪表盘，不直接调用 Playwright。
- **FastAPI 后端**：承载 Agent 生命周期（每次会话创建独立 Agent 实例），通过 MCP Client 与浏览器工具交互，并推送实时事件至前端（SSE/WebSocket）。
- **browser-mcp**：独立的 Python 包/服务，实现 Playwright 操作的 MCP Server，支持远程或本地运行。

---

## 4. 功能需求详述

### 4.1 用户交互流程

1. 用户在 Web 界面输入自然语言指令，如：
   - *打开百度，搜索 LangChain MCP，返回第一条结果的标题*
   - *去 GitHub 查看仓库 langchain-ai/langgraph 的 Star 数*
2. 系统在右栏同步展示“执行状态播报”和最新浏览器截图。
3. Agent 完成操作后，在聊天区域输出最终答案，并附上本次消耗 Token 数。
4. 用户可点击“查看操作回放”，浏览历史步骤的截图序列。

### 4.2 浏览器工具集（MCP Tools）

所有工具通过 `browser-mcp` MCP Server 暴露，**严禁在 Agent 或后端直接使用 Playwright**。

| 工具名 | 功能 | 输入参数 | 输出 | 异常处理 |
|--------|------|----------|------|----------|
| `navigate` | 导航到 URL | `url: str` | `{status, screenshot_base64, title}` | 超时15s后返回 `{error: "timeout", screenshot}` |
| `click` | 点击元素 | `selector: str` | `{status, screenshot_base64}` | 元素未找到/不可点击时：截图 + 返回 `{error: "selector_not_found"}` |
| `type_text` | 输入文本 | `selector: str, text: str` | `{status, screenshot_base64}` | 输入框不存在时同上 |
| `get_content` | 获取页面文本/HTML | `format: "text"或"html"` | `{content, screenshot_base64}` | 白屏返回空内容 |
| `screenshot` | 全页截图 | `full_page: bool = True` | `{screenshot_base64}` | 失败返回空图标记 |
| `scroll` | 滚动页面 | `direction: "up"/"down", amount: int` | `{status, screenshot_base64}` | 无 |
| `execute_script` | 执行自定义 JS（受限） | `script: str` | `{result}` | 用于特殊场景，仅允许安全脚本 |

**每一个工具在返回前，必须在 Server 端自动截图并一并返回**，以便前端展示。

### 4.3 Deep Agent 设计（LangGraph 状态图）

采用 **Plan → Execute → Reflect → (Replan → Execute) → Answer** 的深度规划循环，而非单纯 ReAct。

#### 4.3.1 状态定义 `AgentState`

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # 对话历史
    task: str                                # 原始任务
    plan: list[str]                          # 当前执行计划步骤列表
    execution_log: list[dict]                # 每步执行结果 {step, tool, result, screenshot_path, timestamp}
    retry_count: int                         # 当前步骤重试次数
    need_replan: bool                        # 是否需要重新规划
    final_answer: str                        # 最终答复
    token_usage: dict                        # {"prompt": int, "completion": int}
```

#### 4.3.2 图节点说明
1. plan_node（规划节点）

输入：task, messages

调用 LLM 生成 JSON 格式的执行计划，例如：

```json
[
  "导航到 https://github.com",
  "搜索 langchain-ai/langgraph",
  "提取 Star 数",
  "回答用户"
]
```
将计划写入 state["plan"]，并重置 retry_count=0

2. execute_node（执行节点）

从 plan 中取出当前步骤（列表头），调用对应的 MCP 工具

工具调用方式：通过 langgraph 的 ToolNode 或自定义函数，将工具包装为 LangChain Tool

执行后将结果附加到 execution_log，并从计划中移除该步骤

3. reflect_node（反思节点）

分析最近一次执行结果（execution_log[-1]）

如果成功 → 设置 need_replan=False

如果失败且 retry_count < 2 → 增加计数，返回 execute_node 重新执行（可重试同一操作）

如果失败且计数已达上限 → 设置 need_replan=True，并准备错误描述

特别逻辑：如果错误是 selector_not_found，LLM 会根据失败截图提出新的 selector 候选，写入消息中

4. replan_node（重新规划节点）

当 need_replan=True 时触发

基于当前状态（已执行步骤、失败信息、页面截图）调用 LLM 重新生成剩余计划

将新计划写入 state["plan"]

5. answer_node（回答节点）

根据 execution_log 和原始 task 生成自然语言答案

设置 final_answer

#### 4.3.3 图路由逻辑
```text
START → plan_node → execute_node → reflect_node
                                      ├─ success → answer_node (若计划为空) 或 execute_node (若计划非空)
                                      ├─ retry → execute_node
                                      └─ replan → replan_node → execute_node
answer_node → END
```

### 4.4 后端 API 设计 (FastAPI)
| 端点	| 方法	| 功能	| 说明
|--------|------|----------|------|
| /chat/stream	| POST	| 执行任务并 SSE 推送实时事件	| 请求体 {task, session_id}，返回流式 JSON 事件
| /history/{session_id}	| GET	| 获取某次会话的完整执行日志	| 用于回放
| /replay/{session_id}	| GET	| 返回所有截图步骤列表	| 前端展示截图序列
/health	| GET	| 健康检查	| -

**SSE 事件格式示例：**

```json
{"event": "step_start", "data": {"step": "导航到百度"}}
{"event": "screenshot", "data": {"base64": "...", "timestamp": "..."}}
{"event": "step_end", "data": {"step": "导航完成", "result": "..."}}
{"event": "token_update", "data": {"prompt": 120, "completion": 30}}
{"event": "final_answer", "data": {"content": "...", "total_tokens": 150}}
{"event": "error", "data": {"message": "..."}}
```

### 4.5 前端界面 (Streamlit)
- **左侧聊天区 (70%)：**

对话历史气泡（用户自然语言 / Agent 最终答案）

输入框与发送按钮

- **右侧监控面板 (30%)：**

当前步骤描述（如“正在搜索...”）

浏览器截图实时显示（通过 st.image 更新 base64 图片）

Token 消耗计数器

操作回放下拉菜单（选择历史 session，播放截图序列）

- **启动参数：**

可通过 st.sidebar 配置后端 API 地址（默认 http://localhost:8000）

## 5. 非功能性需求
### 5.1 异常处理与重试机制
- 网络超时：`navigate` 使用 `asyncio.wait_for` + 指数退避重试（最多2次）。

- 元素定位失败：`click` / `type_text` 若失败，必须将失败截图和前一步截图（若有） 一并记录，并在 reflection 时将截图传入 LLM 视觉模型，尝试重新生成 selector。

- 全局弹窗处理：浏览器启动时配置 `--disable-notifications`；每次操作前调用 `dismiss_dialogs` 辅助函数。

- 浏览器进程管理：每个会话结束后，强制关闭浏览器上下文及进程，避免资源泄漏。

### 5.2 可观测性
- **结构化日志**：所有后端、Agent、MCP 的日志统一使用 `loguru`，包含 `request_id` 字段串联全链路。

- **截图留存**：所有操作截图保存至 `data/screenshots/{session_id}/{step_index}.png`，便于事后分析。

- **Token 用量追踪**：通过 LangChain 的回调机制统计每次 LLM 调用的 token 消耗，并累计到状态中，实时广播至前端。

- **Prometheus 指标（可选）**：暴露 `/metrics`，包含工具调用次数、失败率、平均耗时等。

### 5.3 安全策略
- 禁止访问本地文件协议（`file://`）。

- 域名白名单：默认允许 `*.github.com`, `*.baidu.com`, `*.wikipedia.org`，可通过环境变量扩展。

- 所有用户输入在进入 Agent 前做简单过滤（防止注入大量垃圾字符）。

### 5.4 性能要求（演示环境）
- 单次任务总耗时 < 30 秒（含网络延迟）。

- 后端支持同时运行 2 个并发会话（演示用，不做极致并发优化）。

## 6. 项目目录结构
```text
browsepilot/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI 入口
│   │   ├── agent/
│   │   │   ├── deepagent.py    # deepagent定义
│   │   │   ├── tools.py          # 将 MCP 工具转为 LangChain Tool
│   │   │   └── state.py          # AgentState 类型
│   │   ├── mcp_client.py         # 连接 browser-mcp 的客户端
│   │   ├── events.py             # SSE 事件定义
│   │   └── config.py             # 配置加载（pydantic Settings）
│   └── requirements.txt
├── browser_mcp/                  # 独立的 MCP Server 包
│   ├── server.py                 # MCP Server 实现 (mcp.server)
│   ├── browser_manager.py        # Playwright 实例管理
│   └── tools/
│       ├── navigate.py
│       ├── click.py
│       └── ...
├── frontend/
│   └── streamlit_app.py          # Streamlit 界面
├── data/
│   └── screenshots/              # 运行时截图存储
├── pyproject.toml                # 整个项目的依赖管理
├── .env.example
└── README.md
```
**说明**：`browser_mcp` 作为独立的 MCP Server，可以被任何 MCP 客户端（如 Claude Desktop 或自定义后端）直接调用，体现了可复用性。

## 7. 开发阶段与实现要点
### 7.1 第一阶段：MCP Server + Playwright 工具打通
- 实现 `browser_mcp/server.py`，定义 7 个工具。

- 确保每个工具返回 base64 截图和操作结果。

- 编写单元测试：启动浏览器 → 导航 → 截图 → 关闭。

### 7.2 第二阶段：Deep Agent 核心
- 实现 `deepagent.py` ，先用模拟工具（不连真实浏览器）验证规划-执行-反思流程。
deepagent使用可参考地址：https://docs.langchain.com/oss/python/deepagents/overview

- 集成 `mcp_client.py`，通过 MCP 协议动态获取工具列表并绑定到 Agent。

- 添加回调记录 token。

### 7.3 第三阶段：后端 API 与 SSE
- 在 `main.py` 中实现 `/chat/stream` 端点，创建 SSE 通道。

- 每次请求创建新的 Agent 实例和 MCP 连接。

- 实时推送事件（步骤、截图、token）。

### 7.4 第四阶段：Streamlit 前端
- 构建 UI，消费 SSE 流，动态更新截图和状态。

- 实现会话历史和回放功能。

### 7.5 第五阶段：异常测试与文档
- 主动构造失败场景（错误 selector、超时），验证重试和重规划逻辑。

- 编写 README，包含架构图、演示 GIF、启动说明。

## 8. 环境变量配置
在 `.env` 中：

```text
# LLM API
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# MCP 服务器地址（本机 localhost 或远程）
MCP_SERVER_URL=http://localhost:8090

# 浏览器配置
BROWSER_HEADLESS=true
BROWSER_TIMEOUT=15000

# 允许的域名白名单（逗号分隔）
ALLOWED_DOMAINS=github.com,baidu.com,wikipedia.org

# 日志级别
LOG_LEVEL=INFO
```

## 9. 交付与演示要点
### 9.1 GitHub 仓库必备文件
- `README.md`：顶部放置 15 秒演示 GIF，包含架构图和快速启动命令。

- `pyproject.toml`：锁定所有依赖。

- `.env.example`：提供需自行填写的变量。

- `CONTRIBUTING.md`（可选）：说明如何扩展工具。

### 9.2 面试演示脚本（已经替你设计好）
1. **正常流程**：输入“打开 GitHub 搜索 langgraph 的 star 数”，展示流畅截图和最终答案。

2. **主动演示容错**：提前准备好一个“过时的 selector”，当场输入，观察 Agent 重试、重规划、最终返回友好错误信息。

3. **架构讲解**：切换至回放页面，展示每一步截图和日志，强调“全链路可观测，问题秒级回溯”。