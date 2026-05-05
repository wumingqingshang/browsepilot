# BrowsePilot

具备深度规划与自省能力的浏览器自动化 AI 个人助理。通过自然语言指令操控真实浏览器，自主完成网页搜索、信息提取、多步交互等任务。

## 架构

```
Vue3 SPA / Streamlit FE ← HTTP/SSE → FastAPI Backend ← MCP/SSE → browser-mcp (Playwright)
```

- **browser-mcp**: 独立 MCP Server，封装 住 8 个 Playwright 浏览器工具（SSE + stdio 双模式）
- **FastAPI Backend**: LangGraph Agent (Plan→Execute→Reflect→Replan→Answer) + SSE 实时事件流 + 会话管理 API
- **Vue3 Frontend**: 标准前后端分离 SPA，支持会话管理（新建/列表/回放含文本/删除）
- **Streamlit Frontend**: 原版 Python 前端，保留可用

## 快速启动

### 前置条件

- Python 3.11+
- [DeepSeek API Key](https://platform.deepseek.com/)

### 1. 安装依赖

```bash
# Python 后端依赖
uv venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate
uv pip install fastapi uvicorn sse-starlette langgraph langchain langchain-openai mcp playwright streamlit loguru pydantic pydantic-settings httpx python-dotenv
playwright install chromium

# Vue3 前端依赖
cd frontend-vue
npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY=sk-your-deepseek-key
```

### 3. 启动服务

**方式一：一键启动**
```bash
# Windows
start_all.bat

# macOS / Linux
bash start_all.sh
```

**方式二：分别启动**

```bash
# 终端 1: 启动 browser-mcp (端口 8090)
python -m browser_mcp.server

# 终端 2: 启动后端 (端口 8000)
cd backend && uvicorn app.main:app --port 8000

# 终端 3: 启动 Vue3 前端 (端口 5173) — 推荐
cd frontend-vue && npm run dev

# 终端 3 (备选): 启动 Streamlit 前端 (端口 8501)
streamlit run frontend/streamlit_app.py
```

打开浏览器访问 **http://localhost:5173**（Vue3）或 **http://localhost:8501**（Streamlit）

## 项目结构

```
browsepilot/
├── browser_mcp/              # 独立 MCP Server 包
│   ├── server.py             # MCP Server 入口 (SSE + stdio)
│   ├── browser_manager.py    # Playwright 生命周期管理
│   └── tools/                # 7 个浏览器工具
├── backend/                  # FastAPI + LangGraph Agent
│   └── app/
│       ├── main.py           # API 入口 + /chat/stream SSE
│       ├── agent/            # Agent 状态机 (graph, nodes, state, tools)
│       ├── mcp_client.py     # MCP SSE 客户端
│       ├── events.py         # SSE 事件定义
│       ├── session_manager.py # 会话持久化
│       └── config.py         # Pydantic 配置
├── frontend/                 # Streamlit 界面
│   └── streamlit_app.py
├── frontend-vue/             # Vue3 SPA 前端（推荐）
│   └── src/
│       ├── components/       # 11 个 Vue3 组件
│       ├── stores/           # Pinia 状态管理
│       ├── composables/      # useSSE 组合式函数
│       ├── api/              # SSE + REST API 封装
│       └── types/            # TypeScript 类型定义
├── data/                     # 运行时数据 (会话 JSON + 截图)
├── mcp_settings.json         # MCP 连接配置
├── pyproject.toml
└── .env.example
```

## 演示脚本

### 1. 正常流程
输入：*"打开百度，搜索 LangChain MCP，返回第一条结果的标题"*
观察：Agent 自动导航 → 输入 → 搜索 → 提取内容 → 回答

### 2. 容错演示
输入一个不存在的 selector，观察 Agent 自动重试 → 重新规划 → 友好返回错误

### 3. 架构展示
切换回放页面，展示每一步截图和日志，强调全链路可观测性

## 技术栈

| 层级 | 选型 |
|------|------|
| Agent 框架 | LangGraph (StateGraph) |
| LLM | DeepSeek (OpenAI 兼容) |
| 浏览器自动化 | Playwright |
| MCP 协议 | mcp (Python SDK) |
| 后端 | FastAPI + SSE |
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Element Plus |
| 日志 | loguru |
