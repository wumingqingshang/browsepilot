# BrowsePilot 后端 & MCP 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 browser-mcp 从低层 MCP API 迁移到 FastMCP，实现 session 级别的浏览器生命周期，新增 thinking_status SSE 事件让前端展示思考过程。

**Architecture:** browser_mcp/ 拆分为 server.py（定义 FastMCP 实例）和 main.py（启动入口）。工具通过 @mcp.tool() 装饰器自动注册，浏览器通过 lifespan 机制按 session 创建/销毁。后端 events.py 新增 thinking_status 事件，main.py 在每个节点处理前发送状态更新。

**Tech Stack:** FastMCP (mcp 1.27.0), Playwright, Starlette/Uvicorn, SSE StreamingResponse

---

## Task 1: 重写 browser_mcp/server.py

**Files:**
- Rewrite: `browsepilot/browser_mcp/server.py`

- [ ] **Step 1: 替换 server.py 为 FastMCP 架构**

```python
"""browser-mcp FastMCP server — browser automation tools with session-scoped Playwright."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

from browser_mcp.browser_manager import BrowserManager


@asynccontextmanager
async def browser_lifespan(server):
    """每个 MCP session 创建一个独立的浏览器实例，session 结束时自动销毁。"""
    headless = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
    timeout = int(os.getenv("BROWSER_TIMEOUT", "15000"))
    browser = BrowserManager(headless=headless, timeout=timeout)
    await browser.start()
    try:
        yield {"browser": browser}
    finally:
        await browser.stop()


mcp = FastMCP(
    "browser-mcp",
    json_response=True,
    lifespan=browser_lifespan,
    host=os.getenv("MCP_SERVER_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_SERVER_PORT", "8090")),
)
```

- [ ] **Step 2: 验证 server 模块可导入**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -c "from browser_mcp.server import mcp; print(type(mcp).__name__)"
```
Expected: `FastMCP`

- [ ] **Step 3: Commit**

```bash
cd /d/AI_Agent_Demo/browsepilot && git add browser_mcp/server.py && git commit -m "refactor: rewrite server.py with FastMCP and session-scoped browser lifespan"
```

---

## Task 2: 迁移工具文件 — navigate, click, type_text

**Files:**
- Modify: `browsepilot/browser_mcp/tools/navigate.py`
- Modify: `browsepilot/browser_mcp/tools/click.py`
- Modify: `browsepilot/browser_mcp/tools/type_text.py`

- [ ] **Step 1: 迁移 navigate.py**

```python
"""Navigate tool — go to a URL."""

import asyncio

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp
from browser_mcp.tools import validate_url


@mcp.tool()
async def navigate(url: str, ctx: Context) -> dict:
    """Navigate the browser to a URL."""
    browser = ctx.request_context.lifespan_context["browser"]
    is_valid, error = validate_url(url)
    if not is_valid:
        return {"status": "error", "error": error}
    page = await browser.get_page()
    try:
        await asyncio.wait_for(page.goto(url, wait_until="domcontentloaded"), timeout=15)
        title = await page.title()
        screenshot = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot, "title": title}
    except asyncio.TimeoutError:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": "timeout", "screenshot_base64": screenshot}
    except Exception as e:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": str(e), "screenshot_base64": screenshot}
```

- [ ] **Step 2: 迁移 click.py**

```python
"""Click tool — click an element by selector."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def click(selector: str, ctx: Context) -> dict:
    """Click an element identified by a CSS selector."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    await browser.dismiss_dialogs()
    try:
        await page.wait_for_selector(selector, timeout=5000)
        await page.click(selector)
        screenshot = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot}
    except Exception as e:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": "selector_not_found", "detail": str(e), "screenshot_base64": screenshot}
```

- [ ] **Step 3: 迁移 type_text.py**

```python
"""Type text tool — type into an input element."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def type_text(selector: str, text: str, ctx: Context) -> dict:
    """Type text into an input element identified by a CSS selector."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    await browser.dismiss_dialogs()
    try:
        await page.wait_for_selector(selector, timeout=5000)
        await page.fill(selector, text)
        screenshot = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot}
    except Exception as e:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": "selector_not_found", "detail": str(e), "screenshot_base64": screenshot}
```

- [ ] **Step 4: 验证工具注册**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -c "
from browser_mcp.server import mcp
import browser_mcp.tools.navigate
import browser_mcp.tools.click
import browser_mcp.tools.type_text
print('Registered tools:', [t.name for t in mcp._tool_manager.tools.values()])
"
```
Expected: `Registered tools: ['navigate', 'click', 'type_text']`

- [ ] **Step 5: Commit**

```bash
cd /d/AI_Agent_Demo/browsepilot && git add browser_mcp/tools/navigate.py browser_mcp/tools/click.py browser_mcp/tools/type_text.py && git commit -m "refactor: migrate navigate, click, type_text to FastMCP @tool decorator"
```

---

## Task 3: 迁移工具文件 — get_content, screenshot, scroll, execute_script, get_page_structure

**Files:**
- Modify: `browsepilot/browser_mcp/tools/get_content.py`
- Modify: `browsepilot/browser_mcp/tools/screenshot.py`
- Modify: `browsepilot/browser_mcp/tools/scroll.py`
- Modify: `browsepilot/browser_mcp/tools/execute_script.py`
- Modify: `browsepilot/browser_mcp/tools/get_page_structure.py`

- [ ] **Step 1: 迁移 get_content.py**

```python
"""Get content tool — extract page text or HTML."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def get_content(format: str = "text", ctx: Context = None) -> dict:
    """Extract page content as text or HTML."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    try:
        if format == "html":
            content = await page.content()
        else:
            content = await page.inner_text("body")
        screenshot = await browser.screenshot()
        return {"status": "success", "content": content[:10000], "screenshot_base64": screenshot}
    except Exception as e:
        return {"status": "error", "error": str(e), "content": ""}
```

- [ ] **Step 2: 迁移 screenshot.py**

```python
"""Screenshot tool — take a full page screenshot."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def screenshot(full_page: bool = True, ctx: Context = None) -> dict:
    """Take a screenshot of the current page."""
    browser = ctx.request_context.lifespan_context["browser"]
    try:
        data = await browser.screenshot(full_page=full_page)
        if not data:
            return {"status": "error", "error": "screenshot_failed", "screenshot_base64": ""}
        return {"status": "success", "screenshot_base64": data}
    except Exception as e:
        return {"status": "error", "error": str(e), "screenshot_base64": ""}
```

- [ ] **Step 3: 迁移 scroll.py**

```python
"""Scroll tool — scroll the page up or down."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def scroll(direction: str = "down", amount: int = 500, ctx: Context = None) -> dict:
    """Scroll the page up or down by a given pixel amount."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    try:
        pixels = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {pixels})")
        screenshot_data = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot_data}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

- [ ] **Step 4: 迁移 execute_script.py**

```python
"""Execute script tool — run limited safe JavaScript."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp
from browser_mcp.tools import filter_js_script


@mcp.tool()
async def execute_script(script: str, ctx: Context = None) -> dict:
    """Execute a safe JavaScript script on the page."""
    browser = ctx.request_context.lifespan_context["browser"]
    is_safe, error = filter_js_script(script)
    if not is_safe:
        return {"status": "error", "error": error, "result": None}
    page = await browser.get_page()
    try:
        result = await page.evaluate(script)
        return {"status": "success", "result": str(result)}
    except Exception as e:
        return {"status": "error", "error": str(e), "result": None}
```

- [ ] **Step 5: 迁移 get_page_structure.py**

```python
"""Get page structure tool — extract interactive elements with selectors."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def get_page_structure(ctx: Context = None) -> dict:
    """Extract all visible inputs, buttons, and links with their CSS selectors from the current page. Call this before any click/type operation."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    try:
        structure = await page.evaluate("""
            () => {
                const getBestSelector = (el) => {
                    if (el.id) return '#' + CSS.escape(el.id);
                    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                    if (el.className && typeof el.className === 'string') {
                        const cls = el.className.trim().split(/\\s+/)[0];
                        if (cls) return el.tagName.toLowerCase() + '.' + CSS.escape(cls);
                    }
                    const placeholder = el.getAttribute('placeholder');
                    if (placeholder) return el.tagName.toLowerCase() + '[placeholder="' + placeholder + '"]';
                    const ariaLabel = el.getAttribute('aria-label');
                    if (ariaLabel) return el.tagName.toLowerCase() + '[aria-label="' + ariaLabel + '"]';
                    return el.tagName.toLowerCase();
                };

                const inputs = [];
                document.querySelectorAll('input, textarea, select, [contenteditable="true"]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        inputs.push({
                            selector: getBestSelector(el),
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.getAttribute('placeholder') || '',
                            text: (el.value || el.textContent || '').slice(0, 50),
                        });
                    }
                });

                const buttons = [];
                document.querySelectorAll('button, input[type="submit"], input[type="button"], a[role="button"], [role="button"]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        buttons.push({
                            selector: getBestSelector(el),
                            tag: el.tagName.toLowerCase(),
                            text: (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 60),
                            id: el.id || '',
                        });
                    }
                });

                const links = [];
                document.querySelectorAll('a[href]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const text = (el.textContent || '').trim();
                    if (rect.width > 0 && rect.height > 0 && text.length > 0 && text.length < 100) {
                        links.push({
                            selector: getBestSelector(el),
                            text: text.slice(0, 60),
                            href: el.href.slice(0, 200),
                        });
                    }
                });

                return { inputs: inputs.slice(0, 20), buttons: buttons.slice(0, 20), links: links.slice(0, 30) };
            }
        """)
        screenshot = await browser.screenshot()
        return {"status": "success", "structure": structure, "screenshot_base64": screenshot}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

- [ ] **Step 6: 验证全部 8 个工具注册**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -c "
from browser_mcp.server import mcp
import browser_mcp.tools.navigate
import browser_mcp.tools.click
import browser_mcp.tools.type_text
import browser_mcp.tools.get_content
import browser_mcp.tools.screenshot
import browser_mcp.tools.scroll
import browser_mcp.tools.execute_script
import browser_mcp.tools.get_page_structure
names = [t.name for t in mcp._tool_manager.tools.values()]
print('Registered tools:', names)
assert len(names) == 8, f'Expected 8 tools, got {len(names)}'
print('All 8 tools registered successfully')
"
```
Expected: `Registered tools: [...]` and `All 8 tools registered successfully`

- [ ] **Step 7: Commit**

```bash
cd /d/AI_Agent_Demo/browsepilot && git add browser_mcp/tools/get_content.py browser_mcp/tools/screenshot.py browser_mcp/tools/scroll.py browser_mcp/tools/execute_script.py browser_mcp/tools/get_page_structure.py && git commit -m "refactor: migrate remaining 5 tools to FastMCP @tool decorator"
```

---

## Task 4: 清理 browser_mcp/tools/__init__.py

**Files:**
- Modify: `browsepilot/browser_mcp/tools/__init__.py`

- [ ] **Step 1: 删除 register_all_tools 及 handler 代码，只保留安全工具**

```python
"""MCP tool implementations for browser automation."""

import re
from urllib.parse import urlparse

ALLOWED_DOMAINS: list[str] = []


def set_allowed_domains(domains: list[str]) -> None:
    global ALLOWED_DOMAINS
    ALLOWED_DOMAINS = domains


def validate_url(url: str) -> tuple:
    """Validate URL against security policy. Returns (is_valid, error_message)."""
    if not isinstance(url, str):
        return False, "invalid_input: URL must be a string"
    if url.startswith("file://") or url.startswith("file:"):
        return False, "protocol_blocked: file:// protocol is not allowed"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"protocol_blocked: {parsed.scheme} is not allowed"
    if not ALLOWED_DOMAINS:
        return True, ""
    hostname = parsed.hostname or ""
    allowed = any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in ALLOWED_DOMAINS
    )
    if not allowed:
        return False, f"domain_not_allowed: {hostname} is not in whitelist"
    return True, ""


_blocked_pattern = re.compile(
    r'\b(eval|fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage)\b',
    re.IGNORECASE
)


def filter_js_script(script: str) -> tuple:
    """Validate JS script safety. Returns (is_safe, error_message)."""
    if not isinstance(script, str):
        return False, "invalid_input: script must be a string"
    m = _blocked_pattern.search(script)
    if m:
        return False, f"script_blocked: '{m.group(1)}' is not allowed"
    return True, ""
```

- [ ] **Step 2: 验证安全函数和测试仍可用**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -m pytest browser_mcp/tools/test_security.py -v
```
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
cd /d/AI_Agent_Demo/browsepilot && git add browser_mcp/tools/__init__.py && git commit -m "refactor: remove register_all_tools, keep only security validators in __init__.py"
```

---

## Task 5: 创建 browser_mcp/main.py 入口

**Files:**
- Create: `browsepilot/browser_mcp/main.py`

- [ ] **Step 1: 创建 main.py**

```python
"""browser-mcp entry point — load config, register tools, start server."""

import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

from browser_mcp.tools import set_allowed_domains

domains = os.getenv("ALLOWED_DOMAINS", "")
if domains:
    set_allowed_domains([d.strip() for d in domains.split(",")])

# 导入工具模块触发 @mcp.tool() 注册（顺序不重要，noqa 消除 lint 警告）
import browser_mcp.tools.navigate           # noqa: F401
import browser_mcp.tools.click              # noqa: F401
import browser_mcp.tools.type_text          # noqa: F401
import browser_mcp.tools.get_content        # noqa: F401
import browser_mcp.tools.screenshot         # noqa: F401
import browser_mcp.tools.scroll             # noqa: F401
import browser_mcp.tools.execute_script     # noqa: F401
import browser_mcp.tools.get_page_structure # noqa: F401

from browser_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="sse")
```

- [ ] **Step 2: 验证 MCP 服务器可以启动**

```bash
cd /d/AI_Agent_Demo/browsepilot && timeout 5 .venv/Scripts/python -m browser_mcp.main 2>&1 || true
```
Expected: 看到 `Browser starting` 类似的日志（服务启动后会被 timeout 终止，这是正常的）

- [ ] **Step 3: Commit**

```bash
cd /d/AI_Agent_Demo/browsepilot && git add browser_mcp/main.py && git commit -m "feat: add FastMCP entry point with tool auto-registration"
```

---

## Task 6: 端到端验证 — MCP 服务 + 后端连接

**Files:** 无新建/修改

- [ ] **Step 1: 启动 MCP 服务器（后台）**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -m browser_mcp.main &
sleep 3
curl -s http://localhost:8090/sse -H "Accept: text/event-stream" --max-time 3 2>&1 || true
```
Expected: SSE endpoint 有响应（可能是 endpoint 消息或初始化）

- [ ] **Step 2: 验证后端 MCPClient 可以连接并发现工具**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -c "
import asyncio
from backend.app.mcp_client import MCPClient

async def test():
    client = MCPClient('http://localhost:8090/sse')
    tools = await client.connect()
    print('Discovered tools:', [t['name'] for t in tools])
    assert len(tools) == 8
    print('All 8 tools discovered successfully')
    await client.close()

asyncio.run(test())
"
```
Expected: `All 8 tools discovered successfully`

- [ ] **Step 3: 停止 MCP 服务器**

```bash
kill %1 2>/dev/null; pkill -f "browser_mcp.main" 2>/dev/null; echo "done"
```

- [ ] **Step 4: Commit** (无需提交，此任务为验证)

---

## Task 7: 新增 thinking_status SSE 事件

**Files:**
- Modify: `browsepilot/backend/app/events.py`

- [ ] **Step 1: 在 SSEData 类中新增 thinking_status 方法**

在 `events.py` 的 `SSEData` 类中，在 `final_answer` 方法之后添加：

```python
    @staticmethod
    def thinking_status(phase: str, message: str, step_index: int = 0, total_steps: int = 0) -> dict:
        return {"event": "thinking_status", "data": {"phase": phase, "message": message, "step_index": step_index, "total_steps": total_steps}}
```

- [ ] **Step 2: 验证导入**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -c "
from backend.app.events import SSEData
import json
evt = SSEData.thinking_status('planning', '正在分析任务...', 0, 5)
print(json.dumps(evt, ensure_ascii=False))
"
```
Expected: `{"event": "thinking_status", "data": {"phase": "planning", "message": "正在分析任务...", "step_index": 0, "total_steps": 5}}`

- [ ] **Step 3: Commit**

```bash
cd /d/AI_Agent_Demo/browsepilot && git add backend/app/events.py && git commit -m "feat: add thinking_status SSE event for real-time progress display"
```

---

## Task 8: 在 main.py 中发送 thinking_status 事件

**Files:**
- Modify: `browsepilot/backend/app/main.py`

- [ ] **Step 1: 在每个节点处理分支前 yield thinking_status**

修改 `event_generator` 中 `async for event in graph.astream(...)` 循环内的节点处理逻辑，在每个 `if node_name == "xxx":` 分支的最前面插入 `yield SSEData.thinking_status(...)`。

将当前代码（第 82-121 行）中的分支前插入 thinking_status：

```python
            async for event in graph.astream(initial_state, {"recursion_limit": 30}):
                for node_name, node_output in event.items():
                    accumulated_state.update(node_output)
                    if node_name == "plan":
                        yield SSEData.thinking_status("planning", "正在分析任务并制定执行计划...")
                        steps = node_output.get("plan", [])
                        tokens = node_output.get("token_usage", {})
                        yield SSEData.plan_generated(steps, tokens)

                    elif node_name == "execute":
                        if node_output.get("execution_log"):
                            last_log = node_output["execution_log"][-1]
                            step_index = len(node_output["execution_log"]) - 1
                            total = len(accumulated_state.get("plan", [])) + step_index
                            yield SSEData.thinking_status(
                                "executing",
                                f"正在执行: {last_log['step']}",
                                step_index + 1,
                                total if total > step_index else 0,
                            )
                            yield SSEData.step_start(last_log["step"], step_index)
                            result = last_log.get("result", {})
                            if isinstance(result, dict) and result.get("screenshot_base64"):
                                yield SSEData.screenshot(
                                    result["screenshot_base64"],
                                    last_log.get("timestamp", ""),
                                )
                            yield SSEData.step_end(last_log["step"], result)

                    elif node_name == "reflect":
                        yield SSEData.thinking_status("reflecting", "正在反思执行结果...")
                        decision = "replan" if node_output.get("need_replan") else "success"
                        yield SSEData.reflection(decision, "")

                    elif node_name == "replan":
                        yield SSEData.thinking_status("replanning", "正在重新规划替代方案...")
                        yield SSEData.replan(node_output.get("plan", []))

                    elif node_name == "answer":
                        yield SSEData.thinking_status("answering", "正在生成最终回答...")
                        final = node_output.get("final_answer", "")
                        tokens = node_output.get("token_usage", {})
                        total = tokens.get("prompt", 0) + tokens.get("completion", 0)
                        yield SSEData.final_answer(final, total)

                    # Token updates from any node
                    if node_output.get("token_usage"):
                        tu = node_output["token_usage"]
                        yield SSEData.token_update(
                            tu.get("prompt", 0), tu.get("completion", 0)
                        )
```

- [ ] **Step 2: 验证 main.py 语法和导入**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -c "from backend.app.main import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /d/AI_Agent_Demo/browsepilot && git add backend/app/main.py && git commit -m "feat: emit thinking_status SSE events at each agent phase"
```

---

## Task 9: 前后端联调验证

**Files:** 无新建/修改

- [ ] **Step 1: 启动 MCP 服务器（后台）**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -m browser_mcp.main &
sleep 3
echo "MCP server started"
```

- [ ] **Step 2: 启动后端（后台）**

```bash
cd /d/AI_Agent_Demo/browsepilot && .venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
sleep 3
echo "Backend started"
```

- [ ] **Step 3: 用 curl 测试 SSE 流，验证 thinking_status 事件出现**

```bash
curl -s -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"task": "打开百度，搜索hello"}' \
  --max-time 60 2>&1 | grep -o '"event":"thinking_status"[^}]*}' | head -5
```
Expected: 看到多条 `thinking_status` 事件，包含 `planning`、`executing`、`reflecting`、`answering` 等 phase

- [ ] **Step 4: 停止所有服务**

```bash
kill %1 %2 2>/dev/null; pkill -f "browser_mcp.main" 2>/dev/null; pkill -f "uvicorn backend" 2>/dev/null; echo "done"
```

- [ ] **Step 5: Commit** (无需提交，此任务为验证)

---

## 完成检查清单

- [ ] 8 个工具全部以 `@mcp.tool()` 装饰器注册
- [ ] `register_all_tools` / `handle_list_tools` / `handle_call_tool` / `TOOL_HANDLERS` 已删除
- [ ] 浏览器在 session 级别创建和销毁（不在 MCP 启动时）
- [ ] 后端 MCPClient 连接 FastMCP SSE transport 正常工作
- [ ] `thinking_status` SSE 事件在所有 5 个节点阶段发送
- [ ] 安全函数（validate_url, filter_js_script）及测试正常
- [ ] 原有 `browser_mcp/server.py` 中的 `run_sse`/`run_stdio`/`main` 已删除
