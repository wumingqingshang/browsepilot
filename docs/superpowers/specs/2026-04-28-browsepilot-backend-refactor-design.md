# BrowsePilot 后端 & MCP 重构设计

日期：2026-04-28

## 概述

本次重构聚焦后端和 MCP 层，解决三个核心问题：MCP 工具代码现代化、浏览器生命周期管理、后端思考过程可见性。

前线端布局/风格重设计将在第二阶段单独处理。

## 1. MCP FastMCP 重构

### 当前问题
- 使用低层 MCP API：`@server.list_tools()` + `@server.call_tool()` 手动注册
- `server.py` 内手动搭建 Starlette + uvicorn（~90行），职责混杂
- `tools/__init__.py` 维护 `TOOL_HANDLERS` 字典，工具注册和分发耦合

### 目标架构

```
browser_mcp/
├── main.py              # 入口：加载 .env、读取配置、mcp.run()
├── server.py            # 纯定义：FastMCP 实例 + browser_lifespan
├── browser_manager.py   # Playwright 浏览器管理（几乎不变）
└── tools/
    ├── __init__.py      # 删除 register_all_tools 等（约50行）
    ├── navigate.py      # @mcp.tool() 装饰器
    ├── click.py
    ├── type_text.py
    ├── get_content.py
    ├── screenshot.py
    ├── scroll.py
    ├── execute_script.py
    └── get_page_structure.py
```

### server.py 设计

```python
from mcp.server.fastmcp import FastMCP, Context
from contextlib import asynccontextmanager

@asynccontextmanager
async def browser_lifespan(server):
    browser = BrowserManager(headless=..., timeout=...)
    await browser.start()
    try:
        yield {"browser": browser}
    finally:
        await browser.stop()

mcp = FastMCP(
    "browser-mcp",
    json_response=True,
    lifespan=browser_lifespan,
    host="127.0.0.1",
    port=8090,
)

# 工具在各自的 tools/*.py 中通过 @mcp.tool() 注册
```

### 工具函数签名变更

之前：`async def navigate(browser, url: str) -> dict`

之后：`async def navigate(url: str, ctx: Context) -> str`

浏览器实例通过 `ctx.request_context.lifespan_context["browser"]` 获取。

### main.py 设计

```python
from dotenv import load_dotenv
from browser_mcp.server import mcp

# 加载工具（触发 @mcp.tool() 注册）
import browser_mcp.tools.navigate
import browser_mcp.tools.click
# ...

if __name__ == "__main__":
    mcp.run(transport="sse")
```

### 待删除代码

`browser_mcp/tools/__init__.py` 中的：
- `register_all_tools()`（约33行）
- `handle_list_tools()`（约8行）
- `handle_call_tool()`（约9行）
- `TOOL_HANDLERS` 字典（约9行）
- 所有工具 import（迁移到各工具文件自己的 `@mcp.tool()` 装饰器）

`server.py` 中的：
- `run_sse()`（约16行）
- `run_stdio()`（约8行）
- `main()`（约11行）
- 手动 `BrowserManager` 实例化

## 2. 浏览器生命周期

### 当前问题
- `main()` 调用 `await browser.start()`，浏览器在 MCP 服务启动时立即初始化
- 浏览器常驻直到 MCP 服务关闭，中间从不释放
- 只有一个全局浏览器实例，无法隔离不同 session

### 方案

方案 A（已确认）：浏览器按 session 绑定。

通过 FastMCP 的 `lifespan` 机制实现：
- **Session 建立** → `browser_lifespan` 进入 → `await browser.start()`
- **Tool call** → 通过 `ctx.request_context.lifespan_context["browser"]` 访问
- **Session 断开** → `browser_lifespan` 退出 → `await browser.stop()`

每个 session 有独立的浏览器实例，互不干扰。

### 兼容性

FastMCP SSE transport 使用标准 MCP SSE 协议。
后端 `MCPClient`（`mcp.client.sse.sse_client`）无需任何改动。
每个 `chat/stream` 请求建立独立的 MCP session，对应独立的浏览器实例。

## 3. 后端思考过程可见性

### 当前问题
- 前端只能看到"已完成 X 个步骤"的计数
- 没有步骤清单展示（哪些已完成、哪些待执行）
- 节点执行期间（LLM 推理）前端无反馈，用户误以为卡顿

### 方案

#### 新增 thinking_status SSE 事件

在 `events.py` 中新增：

```python
@staticmethod
def thinking_status(phase: str, message: str, step_index: int = 0, total_steps: int = 0) -> dict:
    return {"event": "thinking_status", "data": {"phase": phase, "message": message, "step_index": step_index, "total_steps": total_steps}}
```

#### main.py 事件发送时机

每个节点开始执行时，发送 `thinking_status` 事件：

| 阶段 | phase | message |
|------|-------|---------|
| plan 开始 | `planning` | "正在分析任务并制定执行计划..." |
| execute 每步 | `executing` | "正在执行: {步骤描述}..." |
| reflect 开始 | `reflecting` | "正在反思执行结果..." |
| replan 开始 | `replanning` | "正在重新规划替代方案..." |
| answer 开始 | `answering` | "正在生成最终回答..." |

实现方式：在 `main.py` 的 `event_generator` 中，每个 `if node_name == "xxx":` 分支内，先 yield `SSEData.thinking_status(...)` 再处理节点输出。

#### 前端展示

- `thinking_status` 事件 → 聊天窗口中显示文字 + loading 旋转动画
- `plan_generated` 事件 → 右侧监控面板渲染步骤清单（已存在）
- 步骤清单渲染：当前步骤高亮、已完成加删除线置灰、未开始保持原样

## 4. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `browser_mcp/server.py` | 重写 | FastMCP 实例 + lifespan |
| `browser_mcp/main.py` | 新建 | 启动入口 |
| `browser_mcp/tools/__init__.py` | 精简 | 删除 register_all_tools 等 |
| `browser_mcp/tools/navigate.py` | 修改 | @mcp.tool() + Context |
| `browser_mcp/tools/click.py` | 修改 | 同上 |
| `browser_mcp/tools/type_text.py` | 修改 | 同上 |
| `browser_mcp/tools/get_content.py` | 修改 | 同上 |
| `browser_mcp/tools/screenshot.py` | 修改 | 同上 |
| `browser_mcp/tools/scroll.py` | 修改 | 同上 |
| `browser_mcp/tools/execute_script.py` | 修改 | 同上 |
| `browser_mcp/tools/get_page_structure.py` | 修改 | 同上 |
| `browser_mcp/tools/test_security.py` | 不变 | 工具组合，可能需要调整 |
| `backend/app/events.py` | 修改 | 新增 thinking_status |
| `backend/app/main.py` | 修改 | 新增 thinking_status 事件发送 |

## 5. 不在本次范围

- 前端布局/风格重设计（第二阶段）
- LLM selector 幻觉问题修复
- 前端步骤清单 UI 实现（属于第二阶段前端改动的一部分）
