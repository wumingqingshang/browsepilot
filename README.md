# BrowsePilot

具备深度规划与自省能力的浏览器自动化 AI 个人助理。通过自然语言指令操控真实浏览器，自主完成网页搜索、信息提取、多步交互等任务。

## 核心能力

### 智能意图分类

用户输入首先经过**小模型分类器**（`SMALL_MODEL`），快速识别三种意图：

| 意图 | 处理路径 | 说明 |
|------|---------|------|
| `chitchat` | classify → answer | 闲聊问候，不触发浏览器 |
| `knowledge_qa` | classify → answer | 知识问答，不触发浏览器 |
| `browser_task` | classify → plan → execute → ... | 浏览器任务，**此时才连接 MCP** |

非浏览器任务完全跳过 MCP 连接和 Agent 循环，节省 token 和延迟。

### Agent 执行流程

```
                   ┌─ chitchat ──────────→ answer ─→ END
START → classify ──┼─ knowledge_qa ──────→ answer ─→ END
                   └─ browser_task ─→ MCP连接 → plan → execute → reflect
                                                           ↑         ↓
                                                           │    ┌────┴────┐
                                                           │    │ 成功？    │
                                                           │    └─────────┘
                                                           │     │        │
                                                           │    是        否
                                                           │     │        │
                                                           │     ▼        ▼
                                                           │  弹出步骤   保留步骤
                                                           │     │        │
                                                           │     ▼        ▼
                                                           └──execute  LLM深度反思
                                                                        │
                                                            ┌───────────┴───────────┐
                                                            │ retry    replan   answer │
                                                            └─────────────────────────┘
```

**关键设计**：

- **步骤只在成功时弹出**：失败步骤保留在 plan 中等待重试（`retry_count` 上限 2 次），避免"失败后直接跳到下一步"的 bug
- **完工检查**：plan 所有步骤执行完毕后，LLM 检查已收集信息是否足以回答用户，不足则自动补充 1-3 步
- **plan 自检**：生成执行计划后追加一次 LLM 评估，验证计划能否满足用户意图

### 两级反思机制

**级别一 — 代码级启发式检查（零 LLM 成本）**：

| 检查项 | 方法 | 阈值 |
|--------|------|------|
| 页面内容过短 | 去 HTML 后统计有效字符 | < 50 字 |
| 域名突变 | 对比导航目标 URL 和实际返回 URL | 域名不一致 |
| 连续相似结果 | 末尾 3 条结果去重比较 | 完全相同 |
| 交互元素过少 | 统计 `get_page_structure` 返回的 inputs + buttons | < 3 个 |

通过 → 继续执行。未通过 → 触发级别二。

**级别二 — LLM 深度反思**：仅在步骤失败或级别一告警时触发，分析错误原因，决策 retry（同步骤重试）/ replan（换方案）/ answer（放弃回答）。

### 容错与熔断

| 保护机制 | 规则 | 触发行为 |
|----------|------|---------|
| 连续失败熔断 | `consecutive_failures >= 3` | 跳过剩余步骤 → answer |
| 停滞检测 | `stagnation_count >= 3` | 强制 answer |
| 重规划上限 | `replan_count >= 2` | 放弃 → answer（部分结果） |
| 重复 plan 检测 | Jaccard 相似度 = 1.0 | 放弃 → answer |
| 相似 plan 告警 | Jaccard 相似度 > 80% | reflect 注入策略变更提示 |
| 步骤数上限预警 | `execution_log >= 25` 步 | 强制 answer，避免 GraphRecursionError |
| 完工检查上限 | 最多 1 次补充步骤 | 防止"不足→补充→再不足"循环 |

### 全链路超时

```
MCP 工具调用 30s → LLM 调用 60s → Session 整体 300s
     ↓                    ↓                    ↓
  error 返回          重试1次→降级        返回部分结果+持久化
```

LLM 超时降级策略：plan → 默认三步骤 / execute → 跳过 / reflect → 默认 answer / replan → 直接 answer。

## 架构

```
┌──────────────────────────────────────────────────────────┐
│                    Vue3 SPA Frontend                     │
│              HTTP/SSE (Session, Chat Stream)              │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│                  FastAPI Backend                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  LangGraph Agent                                 │    │
│  │  classify → plan → execute → reflect/replan → answer │
│  │  State: AgentState (16 tracked fields)           │    │
│  └────────────────────┬────────────────────────────┘    │
│  ┌────────────────────┴────────────────────────────┐    │
│  │  MCPClient (transport abstraction)              │    │
│  │  ├─ StreamableHTTPTransport (active)            │    │
│  │  └─ StdioTransport (reserved)                   │    │
│  └────────────────────┬────────────────────────────┘    │
│  ┌────────────────────┴────────────────────────────┐    │
│  │  SessionManager                                 │    │
│  │  并发限制 · TTL 清理 · 磁盘空间保护              │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────┘
                           │ Streamable HTTP (MCP)
┌──────────────────────────▼───────────────────────────────┐
│                  browser-mcp Server                       │
│  ┌─────────────────────────────────────────────────┐    │
│  │  BrowserPool                                     │    │
│  │  ├─ 预热 (prewarm=2) · 上限 (max=8)              │    │
│  │  ├─ 排队获取 (30s 超时→503)                      │    │
│  │  ├─ 生命周期: 30min / 50次 / 10min空闲回收       │    │
│  │  └─ 健康检查 + 自动补充                           │    │
│  └────────────────────┬────────────────────────────┘    │
│  ┌────────────────────┴────────────────────────────┐    │
│  │  8 Browser Tools                                 │    │
│  │  navigate · click · type_text · get_content      │    │
│  │  get_page_structure · screenshot · scroll        │    │
│  │  execute_script                                  │    │
│  └────────────────────┬────────────────────────────┘    │
│                       │ Playwright                       │
│                       ▼                                  │
│              ┌────────────────┐                         │
│              │  Chromium 实例  │                         │
│              └────────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

### 模型分离

```env
# 共享凭据（默认值）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1

# 大模型 — plan / execute / reflect / replan / answer
BIG_MODEL=deepseek-v4-pro
# BIG_MODEL_API_KEY=      # 可选：使用不同 provider

# 小模型 — classify 意图分类
SMALL_MODEL=deepseek-v4-flash
# SMALL_MODEL_API_KEY=    # 可选：使用不同 provider
```

各模型 api_key/base_url 为空时自动回退到共享凭据。

### 数据生命周期

```
Session 创建 → 执行 → 持久化(JSON) → MCP 断开
                                      ↓
                            schedule_cleanup (TTL=60min)
                                      ↓
                            删除 JSON + 全部截图 + 空目录

启动时：扫描 data/sessions/ → 超过 MAX_SESSIONS_COUNT(100) 个 → 删除最旧
截图前：检查 data/ 总大小 → 超过 MAX_STORAGE_MB(500) → 紧急清理最旧 20%
```

## 快速启动

### 前置条件

- Python 3.11+
- [DeepSeek API Key](https://platform.deepseek.com/)（或其他 OpenAI 兼容 API）

### 1. 安装依赖

```bash
uv venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate
uv pip install fastapi uvicorn sse-starlette langgraph langchain langchain-openai mcp playwright loguru pydantic pydantic-settings httpx python-dotenv
playwright install chromium

# Vue3 前端依赖
cd frontend-vue && npm install
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，至少填入 OPENAI_API_KEY
```

关键配置项见 `.env.example`，包括模型选择、BrowserPool 参数、超时阈值、存储上限等。

### 3. 启动

```bash
# 一键启动
bash start.sh   # macOS / Linux
start.bat       # Windows

# 或分别启动
python -m browser_mcp.main          # 端口 8090
uvicorn backend.app.main:app --port 8000  # 端口 8000
cd frontend-vue && npm run dev      # 端口 5173
```

打开 **http://localhost:5173**

## 项目结构

```
browsepilot/
├── browser_mcp/                  # 独立 MCP Server
│   ├── main.py                   # 入口: 初始化 BrowserPool + 注册工具
│   ├── server.py                 # FastMCP server (Streamable HTTP)
│   ├── browser_pool.py           # BrowserPool: 预热·上限·排队·回收
│   ├── browser_manager.py        # Playwright 生命周期 + 健康检查
│   └── tools/                    # 8 个浏览器工具 (+ asyncio 超时)
├── backend/app/
│   ├── main.py                   # FastAPI 入口 + /chat/stream SSE
│   ├── config.py                 # 配置: 显式 .env 加载 + 启动校验
│   ├── mcp_transport.py          # MCP 传输抽象层
│   ├── mcp_client.py             # MCP 客户端: 连接重试·调用超时
│   ├── session_manager.py        # 会话管理: 并发限制·TTL·空间保护
│   ├── events.py                 # SSE 事件类型
│   └── agent/
│       ├── graph.py              # StateGraph: 6 节点 + 条件路由 + 熔断
│       ├── nodes.py              # 节点实现: 分类·规划·执行·反思·重规划·回答
│       ├── state.py              # AgentState: 16 个追踪字段
│       └── tools.py              # MCP 工具描述生成
├── frontend-vue/                 # Vue3 SPA 前端
├── data/                         # 运行时: 会话 JSON + 截图
├── mcp_settings.json             # MCP 服务目录
└── .env.example
```

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat/stream` | POST | SSE 流式 Agent 执行 |
| `/history/{session_id}` | GET | 会话详情 |
| `/replay/{session_id}` | GET | 回放步骤列表 |
| `/sessions` | GET | 会话列表 |
| `/sessions/{session_id}` | DELETE | 删除会话 |
| `/health` | GET | 健康检查 |

## 技术栈

| 层级 | 选型 |
|------|------|
| Agent 框架 | LangGraph (StateGraph + MemorySaver) |
| LLM | DeepSeek (OpenAI 兼容，大小模型分离) |
| 浏览器自动化 | Playwright (Chromium) |
| MCP 协议 | Streamable HTTP (mcp >= 1.25) |
| 后端 | FastAPI + SSE + asyncio |
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Element Plus |
| 日志 | loguru |
| 配置 | pydantic-settings + python-dotenv |
