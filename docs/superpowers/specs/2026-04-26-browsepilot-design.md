# BrowsePilot 设计文档

**日期**: 2026-04-26
**状态**: 已确认
**来源**: BrowsePilot 需求规格说明书 + 多轮对齐讨论

---

## 1. 整体架构

```
┌─────────────────────┐     HTTP/SSE      ┌──────────────────────┐     MCP/SSE      ┌─────────────────────┐
│   Streamlit 前端     │ ◄───────────────► │   FastAPI 后端        │ ◄──────────────► │   browser-mcp        │
│                      │                   │                       │                  │   (独立进程)          │
│  - 聊天区 (70%)      │                   │  - /chat/stream (SSE) │                  │                      │
│  - 监控面板 (30%)    │                   │  - /history/{id}      │                  │  - SSE + stdio 双模式 │
│  - 回放下拉菜单       │                   │  - /replay/{id}       │                  │  - 7 个浏览器工具     │
│  - 侧栏 API 配置      │                   │  - /health            │                  │  - 域名白名单校验     │
└─────────────────────┘                   │                       │                  │  - 自动截图返回       │
                                           │  - LangGraph Agent    │                  └─────────────────────┘
                                           │  - MCP Client         │                           │
                                           │  - Session Manager    │                    Playwright
                                           └──────────────────────┘                   浏览器实例
```

### 核心边界规则
- 前端永远不直接调用 Playwright，只通过后端 API 通信
- 后端永远不直接调用 Playwright，只通过 MCP Client 与 browser-mcp 交互
- browser-mcp 是唯一持有 Playwright 实例的组件
- 安全策略（域名白名单、禁用 file://）全部在 browser-mcp 层硬编码
- Agent 层只做用户输入文本过滤（截断超长输入、过滤控制字符）

---

## 2. 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph (StateGraph) | 直接构建 5 节点状态图，不使用 deepagent 包 |
| LLM | DeepSeek API | 使用 OpenAI 兼容格式，纯文本模型（无视觉能力） |
| 浏览器自动化 | Playwright for Python | 仅 browser-mcp 使用 |
| MCP 协议 | mcp (Python SDK) >= 1.25.0 | SSE + stdio 双模式，项目使用 SSE |
| 后端 | FastAPI >= 0.110 | SSE 流式推送 |
| 前端 | Streamlit >= 1.35 | 免费部署，Python 全栈 |
| 日志 | loguru | 结构化日志，request_id 串联全链路 |
| 包管理 | uv + pyproject.toml | 锁定依赖 |

---

## 3. Agent 状态机设计

### 3.1 状态定义

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # 对话历史
    task: str                                # 原始任务
    plan: list[str]                          # 当前执行计划步骤列表
    execution_log: list[dict]                # 每步执行结果
    retry_count: int                         # 当前步骤重试次数
    need_replan: bool                        # 是否需要重新规划
    final_answer: str                        # 最终答复
    token_usage: dict                        # {"prompt": int, "completion": int}
```

### 3.2 图结构

```
START → plan_node → execute_node → reflect_node
                                        ├─ success + plan空 → answer_node → END
                                        ├─ success + plan非空 → execute_node
                                        ├─ retry(retry_count<2) → execute_node
                                        └─ replan(retry_count≥2) → replan_node → execute_node
```

### 3.3 各节点 LLM 调用策略

| 节点 | LLM 调用 | 视觉能力 | 说明 |
|------|----------|----------|------|
| plan_node | ✅ | 不需要 | 输入 task + 工具列表，输出 JSON 执行步骤数组 |
| execute_node | ❌ | 不需要 | 工具选择与调用，纯工程逻辑 |
| reflect_node | ✅ | 可选（自适应） | 优先传入截图 base64，模型不支持视觉时仅用文本日志 |
| replan_node | ✅ | 可选（自适应） | 同 reflect_node 策略 |
| answer_node | ✅ | 不需要 | 汇总 execution_log，生成自然语言答案 |

### 3.4 视觉能力自适应机制

reflect_node 和 replan_node 执行时：

1. 读取 execution_log[-1] 获取最近执行结果
2. 检查配置中的 `LLM_VISION_ENABLED` 标志
3. 若 VISION_ENABLED=true：尝试读取截图 base64 → 成功则传入 LLM 辅助分析 → 失败则记录警告日志，降级为纯文本分析，继续任务
4. 若 VISION_ENABLED=false：仅基于 execution_log 中的文本信息（tool、result、error、timestamp）做分析
5. 分析完成 → 输出成功/重试/重规划决策

### 3.5 execute_node 细节

execut_node 不是 LangGraph 内置 ToolNode，而是自定义节点：
- 从 state.plan 中取出第一个步骤文本
- 将步骤文本 + 可用 MCP 工具列表传给 LLM 做工具选择
- 调用选中的 MCP 工具
- 结果追加到 execution_log，步骤从 plan 中移除
- 工具调用结果中的截图 base64 写入 execution_log

---

## 4. MCP 传输设计

### 4.1 模式支持
browser-mcp 同时支持 stdio 和 SSE 两种传输模式：
- **stdio**: 用于本地开发调试，通过子进程 stdin/stdout 通信
- **SSE**: 本项目使用，MCP Server 独立监听 HTTP 端口（默认 8090）

### 4.2 mcp_settings.json 配置
项目根目录或 backend 目录下的 `mcp_settings.json`：
```json
{
  "mcpServers": {
    "browser-mcp": {
      "type": "sse",
      "url": "http://localhost:8090"
    }
  }
}
```
FastAPI 后端启动时读取此配置，通过 MCP Client（SSE 模式）连接到 browser-mcp。

---

## 5. SSE 事件流设计

### 5.1 事件类型

| 事件 | 触发时机 | 数据 |
|------|----------|------|
| `plan_generated` | plan_node 完成 | steps, token_usage |
| `step_start` | 执行步骤开始 | step, step_index |
| `screenshot` | 工具返回截图 | base64, timestamp |
| `step_end` | 执行步骤完成 | step, result |
| `reflection` | reflect_node 决策 | decision(success/retry/replan), reason |
| `replan` | 重新规划完成 | new_steps |
| `token_update` | LLM 调用完成 | prompt, completion |
| `final_answer` | answer_node 完成 | content, total_tokens |
| `error` | 异常发生 | message |

### 5.2 SSE 端点
`POST /chat/stream` — 请求体 `{task, session_id?}`，未提供 session_id 则自动生成 UUID。返回 SSE 流。

---

## 6. 会话持久化设计

采用方案 A：内存 + JSON 文件。

- Agent 完成后，将完整 execution_log + final_answer + token_usage 序列化到 `data/sessions/{session_id}.json`
- 所有截图保存至 `data/screenshots/{session_id}/{step_index}.png`
- 回放 API：`GET /history/{session_id}` 返回 JSON，`GET /replay/{session_id}` 返回截图路径列表
- 会话完成后 60 分钟自动清理浏览器上下文和临时资源

---

## 7. 安全策略

| 策略 | 实现位置 | 方式 |
|------|----------|------|
| 禁止 file:// 协议 | browser-mcp | navigate 工具硬编码校验 |
| 域名白名单 | browser-mcp | ALLOWED_DOMAINS 环境变量，解析 hostname 比对 |
| 用户输入过滤 | FastAPI 后端 | 截断 >2000 字符，过滤控制字符 |
| 浏览器启动参数 | browser-mcp | --disable-notifications, --disable-popup-blocking |
| 弹窗处理 | browser-mcp | 每次操作前自动 dismiss |
| JavaScript 安全 | browser-mcp | execute_script 黑名单: eval, fetch, XMLHttpRequest |

---

## 8. 错误处理与重试

### 8.1 分层错误处理
- **用户输入层（FastAPI）**: 空/超长输入 → 400 Bad Request
- **Agent 层（LangGraph）**: LLM 调用失败 → 指数退避重试（最多 2 次）→ 仍失败则 final_answer 返回友好错误
- **MCP 层（browser-mcp）**: 15s 超时 + 指数退避重试（最多 2 次）；selector_not_found 返回错误 + 截图；浏览器崩溃自动重启上下文
- **资源层**: 会话结束/超时 60min → 强制清理

### 8.2 重试策略
- 第 1 次重试：等待 2s
- 第 2 次重试：等待 4s
- 全部失败：转入 replan_node

### 8.3 截图容错
- 截图读取失败不阻断任务
- 记录 warning 后降级为纯文本分析
- 视觉模型调用失败自动降级

---

## 9. 项目目录结构

```
browsepilot/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI 入口
│   │   ├── agent/
│   │   │   ├── graph.py           # LangGraph 状态图定义
│   │   │   ├── nodes.py           # 5 个节点实现
│   │   │   ├── tools.py           # 将 MCP 工具转为 LangChain Tool
│   │   │   └── state.py           # AgentState 类型
│   │   ├── mcp_client.py          # 连接 browser-mcp 的 SSE 客户端
│   │   ├── events.py              # SSE 事件定义
│   │   ├── session_manager.py     # 会话生命周期管理
│   │   └── config.py              # 配置加载（pydantic Settings）
│   └── requirements.txt
├── browser_mcp/                   # 独立的 MCP Server 包
│   ├── server.py                  # MCP Server 入口（SSE + stdio）
│   ├── browser_manager.py         # Playwright 实例管理
│   └── tools/
│       ├── __init__.py
│       ├── navigate.py
│       ├── click.py
│       ├── type_text.py
│       ├── get_content.py
│       ├── screenshot.py
│       ├── scroll.py
│       └── execute_script.py
├── frontend/
│   └── streamlit_app.py           # Streamlit 界面
├── data/
│   ├── sessions/                  # 会话 JSON 持久化
│   └── screenshots/               # 运行时截图存储
├── mcp_settings.json              # MCP 连接配置
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 10. 开发阶段

| 阶段 | 内容 | 依赖 |
|------|------|------|
| Phase 1 | browser-mcp Server + Playwright 工具打通 | 无 |
| Phase 2 | LangGraph Agent 核心（5 节点状态机）| Phase 1 |
| Phase 3 | FastAPI 后端 + SSE 流 + 会话持久化 | Phase 2 |
| Phase 4 | Streamlit 前端 | Phase 3 |
| Phase 5 | 异常测试 + README + 演示准备 | Phase 4 |
