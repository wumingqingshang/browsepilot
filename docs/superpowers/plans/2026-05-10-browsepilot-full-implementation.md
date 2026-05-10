# BrowsePilot 全量实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实施 9 项需求的全部代码改动：B+C 基础设施层（配置、MCP传输、BrowserPool、数据清理）+ A 层 Agent 流程改造（分类、重试修复、节点优化、健壮性、Token统计）。

**Architecture:** 分两阶段执行。Phase 1（B+C 层）改造 config、MCP 传输、浏览器池、清理机制，作为地基。Phase 2（A 层）在稳定地基上改造 Agent 图结构、6 个节点逻辑、熔断超时、Token 统计。两阶段之间有清晰的接口边界：B+C 层暴露的 MCPClient、SessionManager、config 接口被 A 层消费。

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, LangChain, pydantic-settings, Playwright, MCP (streamable-http)

**关键约定:** 代码设计细节不明晰时，停下来与用户沟通，不擅自决策。

---

## 文件结构总览

```
browsepilot/
├── mcp_settings.json                    ← 新建: MCP 服务目录
├── .env                                 ← 多处修改
├── .env.example                         ← 多处修改
├── .gitignore                           ← +.env
├── backend/app/
│   ├── config.py                        ← 核心改动: 显式加载+校验+模型分离+MCP读取+清理配置+超时配置
│   ├── mcp_transport.py                 ← 新建: StreamableHTTPTransport + StdioTransport 骨架
│   ├── mcp_client.py                    ← 适配 transport + 超时/重试
│   ├── session_manager.py               ← 清理逻辑 + 并发限制
│   └── agent/
│       ├── state.py                     ← +10 新字段, token_usage 累加结构
│       ├── graph.py                     ← classify 节点 + 条件路由 + lazy MCP + recursion_limit 预警
│       ├── nodes.py                     ← 6 节点全部改动 + JSON 解析健壮性 + Token 累加 + 上下文压缩（核心）
│       └── tools.py                     ← 移除 langchain_tools 转换层
├── browser_mcp/
│   ├── main.py                          ← streamable-http + BrowserPool 初始化
│   ├── server.py                        ← lifespan 从池获取
│   ├── browser_pool.py                  ← 新建: BrowserPool
│   ├── browser_manager.py               ← +reset()
│   └── tools/
│       ├── get_content.py               ← +wait_for 超时
│       ├── get_page_structure.py        ← +wait_for 超时
│       ├── screenshot.py                ← +wait_for 超时
│       └── scroll.py                    ← +wait_for 超时
└── backend/app/main.py                  ← lazy MCP + session 超时 + 异常持久化 + state 修复 + SSE 适配
```

---

## Phase 1: B+C 基础设施层

### Task 1: 配置加载显式化 (#9)

**Files:**
- Modify: `browsepilot/backend/app/config.py`
- Modify: `browsepilot/.gitignore`

- [ ] **Step 1: 在 config.py 顶部增加显式 load_dotenv + model_validator 校验**

在现有 `Settings` 类之前插入 load_dotenv 逻辑，在 `Settings` 类内部增加 `check_critical` 校验器：

```python
# config.py 顶部 import 区
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
from pydantic import model_validator
from pydantic_settings import BaseSettings

# 显式加载 .env（在 Settings 定义之前）
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    logger.warning(".env not found at {}", ENV_PATH)


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_vision_enabled: bool = False
    mcp_server_url: str = "http://localhost:8090/mcp"
    mcp_server_port: int = 8090
    mcp_mode: str = "sse"
    browser_headless: bool = True
    browser_channel: str = ""
    browser_timeout: int = 15000
    allowed_domains: str = "github.com,baidu.com,wikipedia.org"
    log_level: str = "INFO"
    data_dir: str = "data"
    session_ttl_minutes: int = 60

    @model_validator(mode="after")
    def check_critical(self):
        if not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. "
                "Set it in .env or as an environment variable."
            )
        return self

    class Config:
        env_file = str(Path(__file__).resolve().parent.parent.parent / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
```

注意：`env_file` 路径保持不变作为双重保险。`mcp_server_url` 默认值从 `/sse` 改为 `/mcp`（配合后续 streamable-http 迁移）。

- [ ] **Step 2: browsepilot/.gitignore 增加 .env 规则**

```gitignore
# 在 browsepilot/.gitignore 末尾追加
.env
```

- [ ] **Step 3: 验证 — 启动后端，确认 api_key 校验生效**

```bash
# 临时注释 .env 中的 OPENAI_API_KEY，启动后端应报错退出
cd browsepilot && python -c "from backend.app.config import settings" 2>&1 | grep -i "OPENAI_API_KEY is required"
```

此时应看到 ValueError 并退出。如果通过说明 .env 加载成功，恢复 api_key。

- [ ] **Step 4: Commit**

```bash
git add browsepilot/backend/app/config.py browsepilot/.gitignore
git commit -m "feat: add explicit .env loading and critical field validation to config"
```

---

### Task 2: MCP 传输抽象层 (#1)

**Files:**
- Create: `browsepilot/backend/app/mcp_transport.py`
- Create: `browsepilot/mcp_settings.json`
- Modify: `browsepilot/backend/app/mcp_client.py`
- Modify: `browsepilot/backend/app/config.py`
- Modify: `browsepilot/browser_mcp/main.py`
- Modify: `browsepilot/.env`
- Modify: `browsepilot/.env.example`

- [ ] **Step 1: 创建 mcp_settings.json**

```json
{
  "mcpServers": {
    "browser-mcp": {
      "type": "streamable-http",
      "url": "http://localhost:8090/mcp"
    }
  }
}
```

- [ ] **Step 2: 创建 mcp_transport.py 传输抽象层**

```python
"""MCP transport abstraction layer. Supports streamable-http, stdio, etc."""

from abc import ABC, abstractmethod
from mcp.client.streamable_http import streamable_http_client
from loguru import logger


class MCPTransport(ABC):
    """Abstract base class for MCP transport implementations."""

    @abstractmethod
    async def connect(self):
        """Establish connection, return (read_stream, write_stream) tuple."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the transport connection."""
        ...


class StreamableHTTPTransport(MCPTransport):
    """Streamable HTTP transport (MCP official recommendation)."""

    def __init__(self, url: str):
        self.url = url
        self._client = None

    async def connect(self):
        logger.info("Connecting via streamable-http to {}", self.url)
        self._client = streamable_http_client(self.url)
        read, write = await self._client.__aenter__()
        return read, write

    async def close(self) -> None:
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing streamable-http transport: {}", e)
            self._client = None


class StdioTransport(MCPTransport):
    """Stdio transport (reserved for future use). NOT tested in this iteration."""

    def __init__(self, command: str, args: list[str] | None = None):
        self.command = command
        self.args = args or []
        self._client = None

    async def connect(self):
        raise NotImplementedError("StdioTransport is reserved for future use")

    async def close(self) -> None:
        pass


def create_transport(server_config: dict) -> MCPTransport:
    """Factory: create transport instance based on server config type."""
    transport_type = server_config.get("type", "streamable-http")
    if transport_type == "streamable-http":
        return StreamableHTTPTransport(url=server_config["url"])
    if transport_type == "stdio":
        return StdioTransport(
            command=server_config["command"],
            args=server_config.get("args", []),
        )
    raise ValueError(f"Unknown transport type: {transport_type}")
```

- [ ] **Step 3: 改造 MCPClient 使用 transport 抽象**

修改 `mcp_client.py` 的构造函数和 `connect`/`close` 方法：

```python
# 关键改动: __init__ 参数从 server_url: str 变为 server_config: dict
# connect() 中 sse_client 替换为 create_transport
# close() 委托给 transport

class MCPClient:
    def __init__(self, server_config: dict | None = None):
        self.server_config = server_config or {}
        self._transport: MCPTransport | None = None
        self._session: ClientSession | None = None
        self._tools: list[dict] = []
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> list[dict]:
        if not self.server_config:
            raise RuntimeError("No MCP server config provided")
        transport = create_transport(self.server_config)
        read, write = await transport.connect()
        self._transport = transport
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        tools_result = await self._session.list_tools()
        self._tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema if hasattr(t, "inputSchema") else {},
            }
            for t in tools_result.tools
        ]
        self._connected = True
        logger.info("Connected via {}, discovered {} tools", type(transport).__name__, len(self._tools))
        return self._tools

    async def close(self) -> None:
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing MCP session: {}", e)
        if self._transport:
            try:
                await self._transport.close()
            except Exception as e:
                logger.warning("Error closing transport: {}", e)
        self._connected = False
        logger.info("MCP client disconnected")

    # call_tool, get_tools_schema, tools property 保持不变
```

- [ ] **Step 4: config.py 新增 load_mcp_servers()，更新 Settings 移除 MCP env 变量**

```python
# 在 config.py 中新增
import json

def load_mcp_servers() -> dict:
    """从 mcp_settings.json 读取 MCP 服务器配置。"""
    path = Path(__file__).resolve().parent.parent.parent / "mcp_settings.json"
    if not path.exists():
        logger.warning("mcp_settings.json not found at {}", path)
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mcpServers", {})

def get_mcp_server_config(server_name: str = "browser-mcp") -> dict:
    """获取指定 MCP server 的配置。"""
    servers = load_mcp_servers()
    if server_name not in servers:
        raise ValueError(f"MCP server '{server_name}' not found in mcp_settings.json")
    return servers[server_name]
```

Settings 类中移除 `mcp_server_url`、`mcp_server_port`、`mcp_mode` 字段。

- [ ] **Step 5: browser_mcp/main.py 改为 streamable-http 传输**

```python
# 仅改动最后一行
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

- [ ] **Step 6: main.py 适配新的 MCPClient 构造方式**

```python
# 原来: mcp_client = MCPClient(settings.mcp_server_url)
# 改为:
mcp_client = MCPClient(get_mcp_server_config("browser-mcp"))
```

注意：此时保持 `mcp_client.connect()` 在 event_generator 内调用（暂不改为 lazy），A 层的 classify 节点会将其改为延迟连接。如果这里先改 lazy 会导致当前无 classify 节点时无法正常工作。

- [ ] **Step 7: 更新 .env 和 .env.example**

移除以下行：
```
MCP_SERVER_URL=http://localhost:8090/sse
MCP_SERVER_PORT=8090
MCP_MODE=sse
```

- [ ] **Step 8: 验证 — 启动 browser_mcp 和 backend，确认 MCP 连接正常**

```bash
# Terminal 1: 启动 browser_mcp
cd browsepilot/browser_mcp && python main.py
# 预期: 日志显示 "streamable-http" 而非 "sse"，监听端口 8090

# Terminal 2: 启动 backend
cd browsepilot/backend && uvicorn backend.app.main:app --port 8000
# 预期: 无 MCP 连接错误，health check 返回 ok
```

- [ ] **Step 9: Commit**

```bash
git add browsepilot/mcp_settings.json browsepilot/backend/app/mcp_transport.py \
        browsepilot/backend/app/mcp_client.py browsepilot/backend/app/config.py \
        browsepilot/browser_mcp/main.py browsepilot/.env browsepilot/.env.example
git commit -m "feat: add MCP transport abstraction + SSE to streamable-http migration"
```

---

### Task 3: BrowserPool 浏览器实例池 (#5)

**Files:**
- Create: `browsepilot/browser_mcp/browser_pool.py`
- Modify: `browsepilot/browser_mcp/browser_manager.py`
- Modify: `browsepilot/browser_mcp/server.py`
- Modify: `browsepilot/browser_mcp/main.py`
- Modify: `browsepilot/backend/app/mcp_client.py`
- Modify: `browsepilot/backend/app/session_manager.py`
- Modify: `browsepilot/backend/app/config.py`
- Modify: `browsepilot/.env.example`

- [ ] **Step 1: 创建 BrowserPool 类**

```python
"""Browser instance pool with pre-warming, lifecycle, and health checks."""

import asyncio
import time
from dataclasses import dataclass, field

from loguru import logger

from browser_mcp.browser_manager import BrowserManager


@dataclass
class PooledBrowser:
    browser_manager: BrowserManager
    created_at: float = field(default_factory=time.time)
    request_count: int = 0
    last_used: float = field(default_factory=time.time)
    is_healthy: bool = True


class BrowserPoolExhausted(Exception):
    """Raised when no browser instance is available within the timeout."""
    pass


class BrowserPool:
    def __init__(
        self,
        max_size: int = 8,
        prewarm: int = 2,
        max_age_minutes: int = 30,
        max_requests: int = 50,
        idle_timeout_minutes: int = 10,
        acquire_timeout: float = 30.0,
        headless: bool = True,
        channel: str | None = None,
        browser_timeout: int = 15000,
    ):
        self.max_size = max_size
        self.prewarm = prewarm
        self.max_age_seconds = max_age_minutes * 60
        self.max_requests = max_requests
        self.idle_timeout_seconds = idle_timeout_minutes * 60
        self.acquire_timeout = acquire_timeout
        self.headless = headless
        self.channel = channel
        self.browser_timeout = browser_timeout

        self._available: asyncio.Queue[PooledBrowser] = asyncio.Queue(max_size)
        self._semaphore = asyncio.Semaphore(max_size)
        self._all_instances: set[PooledBrowser] = set()
        self._prewarmed = False

    async def start(self):
        """Pre-warm the pool with initial instances."""
        logger.info("Starting BrowserPool: pre-warming {} instances", self.prewarm)
        for _ in range(self.prewarm):
            pooled = await self._create_instance()
            self._available.put_nowait(pooled)
        self._prewarmed = True

    async def _create_instance(self) -> PooledBrowser:
        browser = BrowserManager(
            headless=self.headless,
            timeout=self.browser_timeout,
            channel=self.channel,
        )
        await browser.start()
        pooled = PooledBrowser(browser_manager=browser)
        self._all_instances.add(pooled)
        return pooled

    async def acquire(self) -> PooledBrowser:
        # Lazy pre-warm on first call
        if not self._prewarmed:
            await self.start()

        # Try non-blocking get first
        try:
            pooled = self._available.get_nowait()
            if self._is_usable(pooled):
                pooled.request_count += 1
                pooled.last_used = time.time()
                return pooled
            else:
                await self._destroy_instance(pooled)
        except asyncio.QueueEmpty:
            pass

        # Try to create new instance if under max
        if self._semaphore.locked() is False:
            async with self._semaphore:
                pooled = await self._create_instance()
                pooled.request_count = 1
                pooled.last_used = time.time()
                return pooled

        # Pool full: wait in queue
        try:
            pooled = await asyncio.wait_for(
                self._available.get(), timeout=self.acquire_timeout
            )
            if self._is_usable(pooled):
                pooled.request_count += 1
                pooled.last_used = time.time()
                return pooled
            else:
                await self._destroy_instance(pooled)
                raise BrowserPoolExhausted("No healthy instance available")
        except asyncio.TimeoutError:
            raise BrowserPoolExhausted(
                f"No browser available within {self.acquire_timeout}s"
            )

    async def release(self, pooled: PooledBrowser):
        if pooled not in self._all_instances:
            return
        try:
            # Health check: verify browser is still alive
            await pooled.browser_manager.get_page()
            pooled.is_healthy = True
        except Exception as e:
            logger.warning("Browser health check failed: {}", e)
            pooled.is_healthy = False

        if not pooled.is_healthy:
            await self._destroy_instance(pooled)
            # Create replacement
            if len(self._all_instances) < self.max_size:
                new_instance = await self._create_instance()
                self._available.put_nowait(new_instance)
            return

        # Check lifecycle limits
        age = time.time() - pooled.created_at
        if age > self.max_age_seconds or pooled.request_count >= self.max_requests:
            logger.info("Browser instance reached lifecycle limit, destroying")
            await self._destroy_instance(pooled)
            return

        # Reset and return to pool
        await pooled.browser_manager.reset()
        self._available.put_nowait(pooled)

    def _is_usable(self, pooled: PooledBrowser) -> bool:
        if not pooled.is_healthy:
            return False
        age = time.time() - pooled.created_at
        if age > self.max_age_seconds:
            return False
        if pooled.request_count >= self.max_requests:
            return False
        return True

    async def _destroy_instance(self, pooled: PooledBrowser):
        if pooled in self._all_instances:
            self._all_instances.discard(pooled)
        try:
            await pooled.browser_manager.stop()
        except Exception as e:
            logger.warning("Error stopping browser instance: {}", e)

    async def _evict_expired(self):
        """Background task: evict idle/expired instances."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            now = time.time()
            to_evict = []
            for pooled in list(self._all_instances):
                if now - pooled.last_used > self.idle_timeout_seconds:
                    to_evict.append(pooled)
            for pooled in to_evict:
                logger.info("Evicting idle browser instance")
                await self._destroy_instance(pooled)
```

- [ ] **Step 2: BrowserManager 新增 reset() 方法**

```python
# browser_manager.py BrowserManager 类中新增

async def reset(self) -> None:
    """Reset page state for instance reuse. Close extra pages, navigate to blank."""
    if self._context:
        pages = self._context.pages
        for page in pages[1:]:
            try:
                await page.close()
            except Exception:
                pass
        if pages:
            self._page = pages[0]
            try:
                await self._page.goto("about:blank")
            except Exception:
                pass
```

- [ ] **Step 3: server.py lifespan 改为从池获取**

```python
# server.py — 改造 browser_lifespan
# 移除直接创建 BrowserManager 的代码，改为 acquire/release

from browser_mcp.browser_pool import pool  # 模块级单例（在 main.py 中初始化）

@asynccontextmanager
async def browser_lifespan(server):
    pooled = await pool.acquire()
    try:
        yield {"browser": pooled.browser_manager}
    finally:
        await pool.release(pooled)
```

注意：此时 pool 对象需要在此 import 前存在。`pool` 在 `main.py` 中初始化，`server.py` 从模块级引用。如果遇到循环 import，将 `pool = BrowserPool(...)` 放在 `server.py` 中（`main.py` 只负责 import 触发注册）。

- [ ] **Step 4: main.py 初始化 BrowserPool**

```python
# browser_mcp/main.py — 在 mcp.run 之前初始化 pool

import os
from browser_mcp.server import mcp
from browser_mcp.browser_pool import BrowserPool

# 初始化全局 BrowserPool（模块级单例）
pool = BrowserPool(
    max_size=int(os.getenv("BROWSER_POOL_SIZE", "8")),
    prewarm=int(os.getenv("BROWSER_POOL_PREWARM", "2")),
    max_age_minutes=int(os.getenv("BROWSER_MAX_AGE_MINUTES", "30")),
    max_requests=int(os.getenv("BROWSER_MAX_REQUESTS", "50")),
    idle_timeout_minutes=int(os.getenv("BROWSER_IDLE_TIMEOUT", "10")),
    acquire_timeout=float(os.getenv("BROWSER_ACQUIRE_TIMEOUT", "30")),
    headless=os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
    channel=os.getenv("BROWSER_CHANNEL", "") or None,
    browser_timeout=int(os.getenv("BROWSER_TIMEOUT", "15000")),
)

# 注册工具模块（已有，不变）
import browser_mcp.tools.navigate
# ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

为解决循环 import，在 `server.py` 中不 import pool，而是使用延迟引用：

```python
# server.py
from browser_mcp.browser_pool import BrowserPoolExhausted
import browser_mcp.browser_pool as bp_module

@asynccontextmanager
async def browser_lifespan(server):
    # 延迟获取 pool 引用
    pooled = await bp_module.pool.acquire()
    try:
        yield {"browser": pooled.browser_manager}
    finally:
        await bp_module.pool.release(pooled)
```

- [ ] **Step 5: MCPClient 增加重试/超时/健康检查**

```python
# mcp_client.py — call_tool 方法增加超时和重试

import asyncio

class MCPClient:
    # ... 已有代码 ...

    async def call_tool(self, tool_name: str, arguments: dict, timeout: float = 30.0) -> dict:
        if not self._session:
            raise RuntimeError("MCP client not connected")
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool call '{}' timed out after {}s", tool_name, timeout)
            return {"status": "error", "error": "timeout", "message": f"Tool '{tool_name}' timed out"}
        # ... 原有结果解析逻辑不变 ...
```

connect() 中增加重试：

```python
async def connect(self, max_retries: int = 3) -> list[dict]:
    last_error = None
    for attempt in range(max_retries):
        try:
            # ... 原有连接逻辑 ...
            return self._tools
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("MCP connection attempt {} failed, retrying in {}s: {}", attempt + 1, wait, e)
                await asyncio.sleep(wait)
    raise RuntimeError(f"MCP connection failed after {max_retries} attempts: {last_error}")
```

- [ ] **Step 6: SessionManager 增加活跃会话数限制**

```python
# session_manager.py

class SessionManager:
    def __init__(self, max_active_sessions: int = 10):
        self._active_sessions: dict[str, dict] = {}
        self._max_sessions = max_active_sessions
        os.makedirs(f"{settings.data_dir}/sessions", exist_ok=True)
        os.makedirs(f"{settings.data_dir}/screenshots", exist_ok=True)

    def create_session(self, session_id: str) -> dict:
        if len(self._active_sessions) >= self._max_sessions:
            raise HTTPException(status_code=429, detail="Too many active sessions. Please try again later.")
        # ... 原有逻辑 ...
```

- [ ] **Step 7: config.py + .env.example 新增 BrowserPool 配置项**

```python
# Settings 类新增
browser_pool_size: int = 8
browser_pool_prewarm: int = 2
browser_max_age_minutes: int = 30
browser_max_requests: int = 50
browser_idle_timeout: int = 10
browser_acquire_timeout: float = 30.0
mcp_tool_timeout: int = 30
mcp_connect_retries: int = 3
max_active_sessions: int = 10
```

- [ ] **Step 8: 验证 — 启动 browser_mcp，确认日志显示 BrowserPool 初始化**

```bash
cd browsepilot/browser_mcp && python main.py
# 预期日志: "Starting BrowserPool: pre-warming 2 instances"
```

- [ ] **Step 9: Commit**

```bash
git add browsepilot/browser_mcp/browser_pool.py \
        browsepilot/browser_mcp/browser_manager.py \
        browsepilot/browser_mcp/server.py \
        browsepilot/browser_mcp/main.py \
        browsepilot/backend/app/mcp_client.py \
        browsepilot/backend/app/session_manager.py \
        browsepilot/backend/app/config.py \
        browsepilot/.env.example
git commit -m "feat: add BrowserPool with lifecycle management and MCP client hardening"
```

---

### Task 4: 数据清理机制 (#6)

**Files:**
- Modify: `browsepilot/backend/app/session_manager.py`
- Modify: `browsepilot/backend/app/agent/nodes.py`
- Modify: `browsepilot/backend/app/config.py`

- [ ] **Step 1: SessionManager 增加磁盘文件删除方法**

```python
# session_manager.py 新增方法

def _delete_session_files(self, session_id: str):
    """删除会话 JSON + 全部关联截图 + 空目录。"""
    # 1. 读取 session 获取截图列表
    filepath = Path(f"{settings.data_dir}/sessions/{session_id}.json")
    if filepath.exists():
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            for entry in data.get("execution_log", []):
                screenshot_path = entry.get("screenshot_path", "")
                if screenshot_path:
                    try:
                        Path(screenshot_path).unlink(missing_ok=True)
                    except OSError:
                        pass
        except (json.JSONDecodeError, OSError):
            pass
        filepath.unlink(missing_ok=True)

    # 3. 清理截图空目录
    screenshots_dir = Path(f"{settings.data_dir}/screenshots")
    session_screenshots = screenshots_dir / session_id
    if session_screenshots.exists():
        try:
            session_screenshots.rmdir()  # 只在空目录时成功
        except OSError:
            pass
```

- [ ] **Step 2: 改造 schedule_cleanup 增加磁盘清理**

```python
async def schedule_cleanup(self, session_id: str, mcp_client=None, delay_minutes: int = None) -> None:
    if delay_minutes is None:
        delay_minutes = settings.session_ttl_minutes
    await asyncio.sleep(delay_minutes * 60)

    # 1. 清理磁盘文件（新增）
    self._delete_session_files(session_id)

    # 2. 清理内存（已有）
    if session_id in self._active_sessions:
        del self._active_sessions[session_id]

    # 3. 断开 MCP（已有）
    if mcp_client:
        await mcp_client.close()

    logger.info("Session {} cleaned up after {} minutes", session_id, delay_minutes)
```

- [ ] **Step 3: 新增启动时清理方法**

```python
def cleanup_on_startup(self):
    """启动时扫描并清理超出上限的旧会话和孤立截图。"""
    max_count = getattr(settings, 'max_sessions_count', 100)
    sessions_dir = Path(f"{settings.data_dir}/sessions")
    if not sessions_dir.exists():
        return

    sessions = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if len(sessions) > max_count:
        for old in sessions[: -(max_count)]:
            session_id = old.stem
            logger.info("Startup cleanup: removing old session {}", session_id)
            self._delete_session_files(session_id)

    # 清理孤立截图
    self._cleanup_orphan_screenshots()


def _cleanup_orphan_screenshots(self):
    """删除无对应 session 的截图目录。"""
    screenshots_dir = Path(f"{settings.data_dir}/screenshots")
    if not screenshots_dir.exists():
        return
    for child in screenshots_dir.iterdir():
        if child.is_dir():
            session_json = Path(f"{settings.data_dir}/sessions/{child.name}.json")
            if not session_json.exists():
                import shutil
                shutil.rmtree(child, ignore_errors=True)
                logger.info("Removed orphan screenshots: {}", child)
```

- [ ] **Step 4: 新增截图写入前空间检查**

```python
def check_storage_before_write(self) -> bool:
    """检查 data/ 目录空间，超限时触发紧急清理。返回是否可以写入。"""
    max_storage_mb = getattr(settings, 'max_storage_mb', 500)
    total_size = self._get_data_dir_size()
    if total_size > max_storage_mb * 1024 * 1024:
        logger.warning("Storage {} MB exceeds limit {} MB, triggering emergency cleanup",
                       total_size // (1024 * 1024), max_storage_mb)
        self._emergency_cleanup(ratio=0.2)
        if self._get_data_dir_size() > max_storage_mb * 1024 * 1024:
            logger.warning("Storage still full after cleanup, skipping screenshot")
            return False
    return True


def _get_data_dir_size(self) -> int:
    total = 0
    data_dir = Path(settings.data_dir)
    if not data_dir.exists():
        return 0
    for f in data_dir.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def _emergency_cleanup(self, ratio: float = 0.2):
    """删除最旧 ratio 比例的会话以释放空间。"""
    sessions_dir = Path(f"{settings.data_dir}/sessions")
    if not sessions_dir.exists():
        return
    sessions = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    to_delete = int(len(sessions) * ratio)
    for old in sessions[:to_delete]:
        self._delete_session_files(old.stem)
```

- [ ] **Step 5: nodes.py 截图保存前增加空间检查**

在 `execute_node` 保存截图前调用：

```python
# 在截图保存逻辑之前
from backend.app.session_manager import session_manager

if not session_manager.check_storage_before_write():
    logger.warning("Skipping screenshot due to storage limit")
else:
    # 原有截图保存逻辑
    ...
```

- [ ] **Step 6: config.py 新增数据清理配置项**

```python
# Settings 类新增
max_sessions_count: int = 100
max_storage_mb: int = 500
cleanup_interval_hours: int = 6
```

- [ ] **Step 7: Commit**

```bash
git add browsepilot/backend/app/session_manager.py \
        browsepilot/backend/app/agent/nodes.py \
        browsepilot/backend/app/config.py
git commit -m "feat: add disk session cleanup, startup scan, and storage protection"
```

---

## Phase 2: A 层 Agent 流程改造

### Task 5: 模型配置重构（SMALL_MODEL / BIG_MODEL）

**Files:**
- Modify: `browsepilot/backend/app/config.py`
- Modify: `browsepilot/backend/app/agent/nodes.py`
- Modify: `browsepilot/.env`
- Modify: `browsepilot/.env.example`

- [ ] **Step 1: config.py 模型字段重构**

将 `llm_model` 替换为 `big_model` + `small_model`，各带可选覆盖凭据：

```python
# Settings 类中
# 移除: llm_model: str = "deepseek-chat"
# 新增:

# 共享凭据（已有，不变）
openai_api_key: str = ""
openai_base_url: str = "https://api.deepseek.com/v1"

# 大模型（主流程）
big_model: str = "deepseek-v4-flash"
big_model_api_key: str = ""   # 空 = fallback 到 openai_api_key
big_model_base_url: str = ""  # 空 = fallback 到 openai_base_url

# 小模型（classify 分类）
small_model: str = "deepseek-chat"
small_model_api_key: str = ""   # 空 = fallback 到 openai_api_key
small_model_base_url: str = ""  # 空 = fallback 到 openai_base_url
```

- [ ] **Step 2: nodes.py 新增 get_small_llm()，修改 get_llm()**

```python
# 修改 get_llm() 使用 big_model 凭据
def get_llm():
    """Get the main (big) LLM instance for plan/execute/reflect/replan/answer."""
    return ChatOpenAI(
        model=settings.big_model,
        api_key=settings.big_model_api_key or settings.openai_api_key,
        base_url=settings.big_model_base_url or settings.openai_base_url,
    )

# 新增 get_small_llm() 用于 classify
def get_small_llm():
    """Get the small LLM instance for intent classification."""
    return ChatOpenAI(
        model=settings.small_model,
        api_key=settings.small_model_api_key or settings.openai_api_key,
        base_url=settings.small_model_base_url or settings.openai_base_url,
    )
```

- [ ] **Step 3: .env 和 .env.example 更新**

```env
# 移除: LLM_MODEL=deepseek-v4-flash
# 新增:
BIG_MODEL=deepseek-v4-flash
# BIG_MODEL_API_KEY=   # 可选
# BIG_MODEL_BASE_URL=  # 可选

SMALL_MODEL=deepseek-chat
# SMALL_MODEL_API_KEY= # 可选
# SMALL_MODEL_BASE_URL=# 可选
```

- [ ] **Step 4: 验证 — 启动 backend 确认模型配置加载**

```bash
cd browsepilot && python -c "
from backend.app.config import settings
print(f'BIG: {settings.big_model}')
print(f'SMALL: {settings.small_model}')
# 验证凭据 fallback
from backend.app.agent.nodes import get_llm, get_small_llm
llm = get_llm()
print(f'LLM model: {llm.model_name}')
"
```

- [ ] **Step 5: Commit**

```bash
git add browsepilot/backend/app/config.py \
        browsepilot/backend/app/agent/nodes.py \
        browsepilot/.env browsepilot/.env.example
git commit -m "feat: separate SMALL_MODEL/BIG_MODEL with per-model credential fallback"
```

---

### Task 6: LLM JSON 解析健壮性

**Files:**
- Modify: `browsepilot/backend/app/agent/nodes.py`
- Modify: `browsepilot/backend/app/agent/state.py`

- [ ] **Step 1: 在 nodes.py 中新增 extract_json() 和 repair_json()**

```python
# nodes.py 顶部新增
import json
import re

def extract_json(text: str) -> str | None:
    """从 LLM 返回文本中提取 JSON 字符串。处理 markdown 包裹和首尾杂文。"""
    # 1. 匹配 ```json ... ``` 或 ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    # 2. 匹配第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return None


def repair_json(candidate: str) -> str:
    """修复常见 JSON 格式错误：尾逗号、单引号 key/value。"""
    # 移除 } 或 ] 前的尾随逗号
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    # 单引号 key: 'key': → "key":
    candidate = re.sub(r"'([^']*)'\s*:", r'"\1":', candidate)
    # 单引号 value: : 'value' → : "value"
    candidate = re.sub(r":\s*'([^']*)'", r': "\1"', candidate)
    return candidate
```

- [ ] **Step 2: 新增 parse_llm_json() 统一入口**

```python
async def parse_llm_json(
    llm,
    messages: list,
    node_name: str,
    fallback: dict,
    max_retries: int = 1,
) -> tuple[dict, dict | None]:
    """统一的 LLM JSON 调用 + 解析 + 容错 + 降级。

    Returns:
        (parsed_dict, token_usage_dict_or_None)
    """
    for attempt in range(max_retries + 1):
        try:
            response = await llm.ainvoke(messages)
            usage = response.usage_metadata
            text = response.content if hasattr(response, "content") else str(response)

            candidate = extract_json(text)
            if candidate is not None:
                try:
                    return json.loads(candidate), usage
                except json.JSONDecodeError:
                    repaired = repair_json(candidate)
                    try:
                        result = json.loads(repaired)
                        logger.info("[{}] JSON repaired successfully", node_name)
                        return result, usage
                    except json.JSONDecodeError as e:
                        logger.warning("[{}] JSON parse failed attempt {}: {}", node_name, attempt + 1, str(e)[:200])

            if attempt < max_retries:
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": "你的回复格式不符合要求。请只返回一个 JSON 对象，不要包含其他内容。",
                })
                continue

        except Exception as e:
            # LLM 调用异常的降级由上层超时机制处理
            logger.error("[{}] LLM call failed: {}", node_name, str(e)[:200])
            raise

    logger.warning("[{}] JSON parse failed after {} retries, using fallback", node_name, max_retries)
    return fallback, None
```

- [ ] **Step 3: AgentState 新增 degradation_log 字段**

```python
# state.py AgentState TypedDict 中新增
degradation_log: list[dict]  # [{"node": "plan", "reason": "json_parse_failed", "timestamp": "..."}]
```

- [ ] **Step 4: 后续任务中逐节点接入 parse_llm_json**

本步骤仅定义工具函数和 state 字段。各节点调用 LLM 处将在后续任务中逐一改为使用 `parse_llm_json()`。

- [ ] **Step 5: Commit**

```bash
git add browsepilot/backend/app/agent/nodes.py browsepilot/backend/app/agent/state.py
git commit -m "feat: add unified LLM JSON parsing with extract/repair/retry/fallback"
```

---

### Task 7: 意图分类路由 (#3)

**Files:**
- Modify: `browsepilot/backend/app/agent/nodes.py`
- Modify: `browsepilot/backend/app/agent/graph.py`
- Modify: `browsepilot/backend/app/agent/state.py`
- Modify: `browsepilot/backend/app/main.py`

- [ ] **Step 1: state.py 新增 intent 字段**

```python
# AgentState TypedDict 新增
intent: str  # "chitchat" | "knowledge_qa" | "browser_task"
```

- [ ] **Step 2: nodes.py 新增 classify_node**

```python
# classify_node 函数，放在 nodes.py 中的其他节点函数之前

CLASSIFY_PROMPT = """你是一个意图分类器。分析用户的输入，判断其意图属于以下哪一种：

1. chitchat — 闲聊、打招呼、与浏览器操作无关的对话
   示例：
   - "你好" / "你是谁" / "今天天气怎么样"
   - "谢谢你" / "再见"

2. knowledge_qa — 需要知识回答的问题，不需要浏览器操作
   示例：
   - "介绍一下机器学习分类方法"
   - "Python 的 GIL 是什么"
   - "比较 React 和 Vue 的优缺点"

3. browser_task — 需要打开浏览器执行具体操作的任务
   示例：
   - "打开百度搜索 LangChain"
   - "帮我在 GitHub 上找 Python 爬虫项目"
   - "看看百度首页有什么内容"

规则：
- 如果用户只是聊天、问候或问你是谁 → chitchat
- 如果用户需要知识解答但不需要浏览器操作 → knowledge_qa
- 如果用户需要打开网页、点击、输入、截图等浏览器操作 → browser_task

返回 JSON 格式：{"intent": "chitchat|knowledge_qa|browser_task"}
只返回 JSON，不要包含任何其他内容。"""


async def classify_node(state: AgentState) -> dict:
    """Classify user intent using the small model."""
    logger.info("[classify_node] Classifying: {}", state["task"][:80])
    llm = get_small_llm()

    result, usage = await parse_llm_json(
        llm=llm,
        messages=[
            SystemMessage(CLASSIFY_PROMPT),
            HumanMessage(content=state["task"]),
        ],
        node_name="classify",
        fallback={"intent": "browser_task"},  # 保守：未知走完整流程
    )

    intent = result.get("intent", "browser_task")
    if intent not in ("chitchat", "knowledge_qa", "browser_task"):
        logger.warning("[classify_node] Unknown intent '{}', defaulting to browser_task", intent)
        intent = "browser_task"

    token_update = accumulate_tokens(state.get("token_usage", {}), usage, "classify") if usage else {}

    return {
        "intent": intent,
        **({"token_usage": token_update} if token_update else {}),
    }
```

- [ ] **Step 3: graph.py 新增 classify 节点 + 条件路由 + MCP lazy 连接**

```python
# graph.py — 重构 build_graph

from backend.app.agent.nodes import (
    plan_node, execute_node, reflect_node, replan_node, answer_node,
    classify_node,  # 新增
)

def build_graph(mcp_client: MCPClient, lazy_mcp: bool = False):
    workflow = StateGraph(AgentState)

    langchain_tools_holder = {"tools": None}

    async def classify(state: AgentState) -> dict:
        return await classify_node(state)

    async def plan(state: AgentState) -> dict:
        # Lazy MCP connect: only connect when browser_task reaches plan
        if lazy_mcp and not mcp_client.is_connected:
            await mcp_client.connect()
        return await plan_node(state, mcp_client)

    # execute, reflect, replan, answer wrappers 保持不变
    async def execute(state: AgentState) -> dict:
        if langchain_tools_holder["tools"] is None:
            langchain_tools_holder["tools"] = await build_tools_from_mcp(mcp_client)
        return await execute_node(state, mcp_client, langchain_tools_holder["tools"])

    async def reflect(state: AgentState) -> dict:
        return await reflect_node(state)

    async def replan(state: AgentState) -> dict:
        return await replan_node(state, mcp_client)

    async def answer(state: AgentState) -> dict:
        return await answer_node(state)

    # Add nodes
    workflow.add_node("classify", classify)
    workflow.add_node("plan", plan)
    workflow.add_node("execute", execute)
    workflow.add_node("reflect", reflect)
    workflow.add_node("replan", replan)
    workflow.add_node("answer", answer)

    # Entry: classify
    workflow.set_entry_point("classify")

    # classify → conditional routing
    workflow.add_conditional_edges(
        "classify",
        _route_classify,
        {
            "chitchat": "answer",
            "knowledge_qa": "answer",
            "browser_task": "plan",
        },
    )

    # 其余边不变
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "reflect")
    workflow.add_edge("replan", "execute")
    workflow.add_edge("answer", END)

    workflow.add_conditional_edges(
        "reflect",
        _route_reflect,
        {"execute": "execute", "replan": "replan", "answer": "answer"},
    )

    return workflow.compile()


def _route_classify(state: AgentState) -> str:
    intent = state.get("intent", "browser_task")
    if intent in ("chitchat", "knowledge_qa"):
        return intent
    return "browser_task"


# _route_reflect 保持不变（后续任务会修改）
```

- [ ] **Step 4: main.py 改为 lazy MCP 连接**

```python
# main.py 中，移除 event_generator 内的 await mcp_client.connect()
# graph 改为 build_graph(mcp_client, lazy_mcp=True)

# 关键改动区域:
mcp_client = MCPClient(get_mcp_server_config("browser-mcp"))

async def event_generator():
    # ...
    graph = build_graph(mcp_client, lazy_mcp=True)  # lazy_mcp=True
    # ...
    # await mcp_client.connect()   ← 删除此行
```

同时为 `classify` 节点增加 SSE 事件：

```python
elif node_name == "classify":
    yield SSEData.thinking_status("classifying", "正在分析用户意图...")
    intent = node_output.get("intent", "unknown")
    yield SSEData.classification(intent)  # 新事件类型
```

- [ ] **Step 5: events.py 新增 classification 事件**

```python
@staticmethod
def classification(intent: str) -> dict:
    return {"event": "classification", "data": {"intent": intent}}
```

- [ ] **Step 6: Commit**

```bash
git add browsepilot/backend/app/agent/nodes.py \
        browsepilot/backend/app/agent/graph.py \
        browsepilot/backend/app/agent/state.py \
        browsepilot/backend/app/main.py \
        browsepilot/backend/app/events.py
git commit -m "feat: add intent classification node with lazy MCP connection"
```

---

### Task 8: execute 重试逻辑修复 (#2)

**Files:**
- Modify: `browsepilot/backend/app/agent/nodes.py`

- [ ] **Step 1: execute_node 条件步骤弹出**

找到 `execute_node` 中 `new_plan = state["plan"][1:]` 的位置，替换为条件判断：

```python
# execute_node 关键改动
result = await mcp_client.call_tool(tool_name, arguments)
success = isinstance(result, dict) and result.get("status") != "error"

if success:
    new_plan = state["plan"][1:]  # 成功：弹出当前步骤
    retry_count = 0
else:
    new_plan = state["plan"]      # 失败：保留当前步骤
    retry_count = state.get("retry_count", 0) + 1

return {
    "plan": new_plan,
    "retry_count": retry_count,
    "consecutive_failures": state.get("consecutive_failures", 0) + (0 if success else 1),
    # ... 其他返回字段
}
```

注意：`consecutive_failures` 字段将在 Task 10 中正式引入 state，此处提前使用 `state.get("consecutive_failures", 0)` 做兼容。

- [ ] **Step 2: 验证逻辑**

手动推演两个场景：
- 步骤成功 → `new_plan = plan[1:]`, `retry_count = 0` → 继续下一步
- 步骤失败 → `new_plan = plan`, `retry_count += 1` → reflect 判重试时重新执行同一步骤

- [ ] **Step 3: Commit**

```bash
git add browsepilot/backend/app/agent/nodes.py
git commit -m "fix: only pop execute step on success, retain on failure for retry"
```

---

### Task 9: Agent 五节点优化 (#4)

**Files:**
- Modify: `browsepilot/backend/app/agent/nodes.py`
- Modify: `browsepilot/backend/app/agent/state.py`

此任务改动集中在 `nodes.py` 五个节点的核心逻辑。由于涉及代码量较大，与用户逐节点确认方案后进行。

- [ ] **Step 1: reflect_node — 两级反思机制**

与用户确认后，实现级别一启发式检查和级别二 LLM 反思。关键结构：

```python
async def reflect_node(state: AgentState) -> dict:
    # 级别一：启发式检查（代码级，不调 LLM）
    heuristic_issues = _run_heuristic_checks(state)
    if heuristic_issues:
        logger.info("[reflect] Heuristic checks found issues: {}", heuristic_issues)

    # 级别二：LLM 深度反思（步骤失败时 或 plan 为空时）
    if state.get("plan") and len(state["plan"]) > 0:
        # 有剩余步骤 → 继续执行（成功路径不调 LLM）
        if not heuristic_issues and not _last_step_failed(state):
            return {"need_replan": False}  # 透传
    else:
        # plan 为空 → 完工检查
        return await _completion_check(state)

    # 有异常 → LLM 反思
    return await _llm_reflection(state, heuristic_issues)
```

> **沟通点：** `_run_heuristic_checks` 和 `_completion_check` 的具体实现将在实施时与用户对齐。

- [ ] **Step 2: plan_node — 自检**

生成计划后追加自检调用：

```python
async def plan_node(state: AgentState, mcp_client) -> dict:
    # 生成 initial_plan（逻辑已有）
    # ...

    # 自检
    self_check_prompt = f"""用户任务：{state["task"]}
已生成的计划：{json.dumps(initial_plan, ensure_ascii=False)}

这个计划执行完毕后，获得的信息能否回答用户的原始问题？
如果不能，请在计划末尾补充缺失的步骤。
返回 JSON：{{"sufficient": true/false, "extra_steps": [...]}}"""

    check_llm = get_llm()
    check_result, _ = await parse_llm_json(
        llm=check_llm,
        messages=[SystemMessage(self_check_prompt)],
        node_name="plan_self_check",
        fallback={"sufficient": True, "extra_steps": []},
    )

    if not check_result.get("sufficient", True):
        extra_steps = check_result.get("extra_steps", [])
        if extra_steps:
            initial_plan.extend(extra_steps)

    # Token 统计
    # ...
```

- [ ] **Step 3: replan_node — 视觉接入**

```python
async def replan_node(state: AgentState, mcp_client) -> dict:
    # 构建上下文
    if settings.llm_vision_enabled:
        context = _build_vision_context(state)
    else:
        context = _build_text_context(state)

    # ... LLM 调用生成 new_plan ...

    # 重复 plan 检测（Task 10 实现，此处预留接口）
```

> **沟通点：** `_build_vision_context` 的具体多模态消息构建方式将在实施时确认。

- [ ] **Step 4: execute_node — 精简 prompt**

将当前 ~30 行 system prompt 压缩为：

```python
EXECUTE_PROMPT = """你是浏览器自动化执行专家。
可用工具：
{tools_desc}

核心规则：
1. 操作页面元素前，必须先用 get_page_structure 获取实际选择器
2. 只使用页面结构中返回的选择器，禁止编造或猜测
3. 一次只执行一个操作

最近执行上下文：
{recent_context}

根据用户任务和当前上下文，选择并执行下一个工具调用。
返回 JSON：{{"tool": "工具名称", "arguments": {{...}}, "step": "步骤描述"}}"""
```

- [ ] **Step 5: answer_node — 边界兜底**

```python
async def answer_node(state: AgentState) -> dict:
    llm = get_llm()

    if not state.get("execution_log"):
        # chitchat / knowledge_qa 直通
        response = await llm.ainvoke([
            SystemMessage("你是BrowsePilot，一个有用的AI助手，精通浏览器自动化。"),
            *state["messages"][-10:],  # 最近 10 条对话
            HumanMessage(content=state["task"]),
        ])
    else:
        # browser_task 路径：使用压缩上下文
        context = build_context_with_budget(
            system_prompt=ANSWER_PROMPT,
            task=state["task"],
            messages=state.get("messages", []),
            execution_log=state["execution_log"],
            page_contents=_extract_page_contents(state["execution_log"]),
        )
        response = await llm.ainvoke([SystemMessage(content=context)])

    token_usage = accumulate_tokens(state.get("token_usage", {}), response, "answer")
    return {
        "final_answer": response.content,
        "token_usage": token_usage,
    }
```

- [ ] **Step 6: state.py 新增 completion_check_count**

```python
completion_check_count: int  # 完工检查次数限制（最多 1 次）
```

- [ ] **Step 7: Commit**

```bash
git add browsepilot/backend/app/agent/nodes.py browsepilot/backend/app/agent/state.py
git commit -m "feat: optimize five agent nodes with reflection, self-check, vision, simplified prompt, fallback"
```

---

### Task 10: 健壮性加固 (#7)

**Files:**
- Modify: `browsepilot/backend/app/agent/state.py`
- Modify: `browsepilot/backend/app/agent/nodes.py`
- Modify: `browsepilot/backend/app/agent/graph.py`
- Modify: `browsepilot/backend/app/main.py`
- Modify: `browsepilot/backend/app/config.py`
- Modify: `browsepilot/browser_mcp/tools/get_content.py`
- Modify: `browsepilot/browser_mcp/tools/get_page_structure.py`
- Modify: `browsepilot/browser_mcp/tools/screenshot.py`
- Modify: `browsepilot/browser_mcp/tools/scroll.py`

- [ ] **Step 1: state.py 新增熔断计数器**

```python
# AgentState TypedDict 新增
consecutive_failures: int    # 连续失败次数
stagnation_count: int        # 停滞计数
replan_count: int            # 重规划次数
stagnation_warning: bool     # reflect 提示注入开关
```

- [ ] **Step 2: nodes.py 实现重复 plan 检测 + reflect 提示注入**

```python
# 新增 compute_plan_similarity()
def compute_plan_similarity(old_plan: list[str], new_plan: list[str]) -> float:
    """Jaccard 相似度，中文按字切分。不调 LLM。"""
    def tokenize(steps):
        tokens = set()
        for s in steps:
            for ch in s.replace(" ", ""):
                tokens.add(ch)
        return tokens
    old_tokens = tokenize(old_plan)
    new_tokens = tokenize(new_plan)
    if not old_tokens or not new_tokens:
        return 0.0
    return len(old_tokens & new_tokens) / len(old_tokens | new_tokens)
```

在 `replan_node` 生成 new_plan 后：

```python
similarity = compute_plan_similarity(state["plan"], new_plan)

if similarity == 1.0:
    return {
        "plan": state["plan"],
        "need_replan": False,
        "stagnation_count": state.get("stagnation_count", 0) + 1,
    }

if similarity > 0.8:
    return {
        "plan": new_plan,
        "stagnation_count": state.get("stagnation_count", 0) + 1,
        "stagnation_warning": True,
        "replan_count": state.get("replan_count", 0) + 1,
        "need_replan": False,
    }

return {
    "plan": new_plan,
    "stagnation_count": 0,
    "stagnation_warning": False,
    "replan_count": state.get("replan_count", 0) + 1,
    "need_replan": False,
}
```

在 `reflect_node` 的 LLM 反思 prompt 中注入：

```python
if state.get("stagnation_warning"):
    system_prompt += """\n\n⚠ 重要警告：上一轮重规划生成的计划与旧计划高度相似。
当前策略可能陷入死循环。请尝试根本上不同的替代方案：
- 改变操作顺序
- 尝试不同的导航路径
- 如果当前页面无法完成任务，考虑回退到搜索引擎重新开始
如果确实没有可行的替代方案，请直接判定 answer。"""
```

- [ ] **Step 3: 各节点增加超时包裹 + 熔断检测**

在 `_route_reflect` 中增加熔断检测：

```python
def _route_reflect(state: AgentState) -> str:
    # 熔断检查
    if state.get("consecutive_failures", 0) >= 3:
        logger.warning("Circuit breaker: {} consecutive failures, forcing answer", state["consecutive_failures"])
        return "answer"
    if state.get("replan_count", 0) >= 2:
        logger.warning("Too many replans ({}), forcing answer", state["replan_count"])
        return "answer"
    if state.get("stagnation_count", 0) >= 3:
        logger.warning("Stagnation detected, forcing answer")
        return "answer"

    # recursion_limit 预警
    if len(state.get("execution_log", [])) >= 25:
        logger.warning("Approaching recursion limit, forcing answer")
        return "answer"

    # 原有逻辑
    if state.get("need_replan"):
        return "replan"
    if state.get("plan") and len(state["plan"]) > 0:
        return "execute"
    return "answer"
```

- [ ] **Step 4: main.py Session 超时 + 异常持久化**

```python
# main.py event_generator 中
try:
    # ... 原有逻辑 ...
    async for event in graph.astream(initial_state, {"recursion_limit": 30}):
        # ... 处理事件 ...

    # 正常持久化
    # ...

except asyncio.TimeoutError:
    logger.warning("Session {} timed out", session_id)
    yield SSEData.error("Session timed out. Partial results are saved.")
    # 保存部分结果
    if accumulated_state:
        session_manager.update(session_id,
            execution_log=accumulated_state.get("execution_log", []),
            final_answer=accumulated_state.get("final_answer", "") or "(会话超时，以下为部分结果)",
            token_usage=accumulated_state.get("token_usage", {}),
        )
    session_manager.persist(session_id)

except Exception as e:
    logger.exception("Error in session {}", session_id)
    yield SSEData.error(str(e))
    # 异常时持久化（新增）
    if accumulated_state:
        session_manager.update(session_id,
            execution_log=accumulated_state.get("execution_log", []),
            final_answer=accumulated_state.get("final_answer", ""),
            token_usage=accumulated_state.get("token_usage", {}),
            status="failed",
        )
        session_manager.persist(session_id)
    try:
        await mcp_client.close()
    except Exception as close_err:
        logger.warning("Error closing MCP after exception: {}", close_err)
```

session 整体超时通过 `asyncio.wait_for` 包裹 graph.astream：

```python
# 用 asyncio.wait_for 包裹 stream 循环
try:
    async for event in asyncio.wait_for(
        _stream_events(graph, initial_state, accumulated_state, session_id),
        timeout=300,
    ):
        yield event
except asyncio.TimeoutError:
    # ...
```

> **沟通点：** `_stream_events` 的封装方式及超时后部分结果的收集方式将在实施时对齐。

- [ ] **Step 5: browser_mcp 工具增加 wait_for 超时**

对 4 个无超时的工具（get_content, get_page_structure, screenshot, scroll），在核心操作外包 `asyncio.wait_for`：

```python
# get_content.py 示例
try:
    content = await asyncio.wait_for(page.evaluate("document.body.innerText"), timeout=15.0)
except asyncio.TimeoutError:
    return {"status": "error", "error": "timeout", "message": "get_content timed out"}
```

- [ ] **Step 6: config.py 新增超时/熔断配置**

```python
# Settings 类新增
llm_timeout_seconds: int = 60
session_timeout_seconds: int = 300
consecutive_failures_threshold: int = 3
stagnation_threshold: int = 3
replan_max_count: int = 2
recursion_warning_threshold: int = 25
```

- [ ] **Step 7: Commit**

```bash
git add browsepilot/backend/app/agent/state.py \
        browsepilot/backend/app/agent/nodes.py \
        browsepilot/backend/app/agent/graph.py \
        browsepilot/backend/app/main.py \
        browsepilot/backend/app/config.py \
        browsepilot/browser_mcp/tools/get_content.py \
        browsepilot/browser_mcp/tools/get_page_structure.py \
        browsepilot/browser_mcp/tools/screenshot.py \
        browsepilot/browser_mcp/tools/scroll.py
git commit -m "feat: add circuit breaker, timeouts, recursion_limit warning, and cleanup hardening"
```

---

### Task 11: Token 统计与上下文管理 (#8)

**Files:**
- Modify: `browsepilot/backend/app/agent/state.py`
- Modify: `browsepilot/backend/app/agent/nodes.py`
- Modify: `browsepilot/backend/app/agent/tools.py`
- Modify: `browsepilot/backend/app/main.py`
- Modify: `browsepilot/backend/app/config.py`

- [ ] **Step 1: state.py token_usage 改为累加结构，新增 total_steps**

```python
# AgentState TypedDict
token_usage: dict  # {"prompt": 0, "completion": 0, "breakdown": {...}}
total_steps: int   # 单调递增截图计数器
```

- [ ] **Step 2: nodes.py 实现 accumulate_tokens() + compress_execution_log() + build_context_with_budget()**

```python
def accumulate_tokens(current: dict, usage, node_name: str) -> dict | None:
    """从 LLM response usage_metadata 提取并累加。"""
    if usage is None:
        return None
    add_prompt = usage.get("input_tokens", 0)
    add_completion = usage.get("output_tokens", 0)
    return {
        "prompt": current.get("prompt", 0) + add_prompt,
        "completion": current.get("completion", 0) + add_completion,
        "breakdown": {
            **current.get("breakdown", {}),
            node_name: {"prompt": add_prompt, "completion": add_completion},
        },
    }


def compress_execution_log(execution_log: list, max_tokens: int = 4000) -> str:
    """压缩执行日志：最近 3 步完整保留，更早步骤只保留步骤名 + 状态。"""
    if len(execution_log) <= 3:
        return "\n".join(
            f"- {e['step']}: {json.dumps(e.get('result', {}), ensure_ascii=False)[:200]}"
            for e in execution_log
        )
    recent = execution_log[-3:]
    older = execution_log[:-3]
    parts = ["## 早期步骤摘要"]
    parts.extend(f"- {e['step']} [{e.get('result', {}).get('status', 'unknown')}]" for e in older)
    parts.append("\n## 最近步骤")
    parts.extend(
        f"- {e['step']}: {json.dumps(e.get('result', {}), ensure_ascii=False)[:300]}"
        for e in recent
    )
    return "\n".join(parts)


def build_context_with_budget(
    system_prompt: str,
    task: str,
    messages: list,
    execution_log: list,
    page_contents: list[str],
    max_tokens: int = 8000,
) -> str:
    """按优先级组装上下文，超出预算从低优先级裁切。"""
    core = system_prompt + "\n\n用户任务：" + task
    budget = max_tokens - len(core) // 2
    if budget <= 0:
        return core[: max_tokens * 2]

    log_budget = min(int(budget * 0.5), 4000)
    log_text = compress_execution_log(execution_log, max_tokens=log_budget)
    budget -= len(log_text) // 2

    content_budget = int(budget * 0.3)
    content_text = ""
    for pc in reversed(page_contents):
        chunk = pc[: content_budget * 2]
        if not chunk:
            break
        content_text = chunk + "\n---\n" + content_text
    budget -= len(content_text) // 2

    msg_text = ""
    max_msgs = getattr(settings, 'max_messages_count', 50)
    for msg in reversed(messages[-max_msgs:]):
        msg_content = getattr(msg, "content", str(msg))
        chunk = msg_content[: max(budget * 2, 200)]
        if not chunk:
            break
        role = getattr(msg, "type", "unknown")
        msg_text = f"{role}: {chunk}\n" + msg_text

    return core + "\n\n" + log_text + "\n\n" + content_text + "\n\n" + msg_text
```

- [ ] **Step 3: 6 个节点全部接入 accumulate_tokens**

在 classify, plan, execute, reflect, replan, answer 每个节点的 LLM 调用之后，调用 `accumulate_tokens()` 并合并到 state 返回中。

- [ ] **Step 4: tools.py 移除 langchain_tools 转换层**

当前 `build_tools_from_mcp()` 创建了从未被 invoke 的 langchain_tools。改为直接从 mcp_client.tools 生成工具描述文本：

```python
# 新的简洁实现
def get_tools_description(mcp_client) -> str:
    """从 MCP 工具元数据直接生成工具描述文本。"""
    lines = []
    for t in mcp_client.tools:
        lines.append(f"- {t['name']}: {t.get('description', '')}")
    return "\n".join(lines)
```

同时更新 graph.py 中 `langchain_tools_holder` 相关逻辑，execute_node 中移除未使用的 langchain_tools 参数。

- [ ] **Step 5: main.py 适配 accumulated_state**

```python
# 替换 accumulated_state = dict(initial_state) + 手工 update
# 改为直接用 graph.astream 返回的完整 state

# event_generator 中:
async for event in graph.astream(initial_state, {"recursion_limit": 30}):
    for node_name, node_output in event.items():
        # node_output 已包含该节点的全部返回字段
        # 用 LangGraph 的 state 追踪来取最终状态
        ...

# 持久化时用最后一次完整的 accumulated_state
```

> **沟通点：** `accumulated_state` 改为 LangGraph 原生状态追踪的具体实现方式，在实施时与用户对齐。

- [ ] **Step 6: config.py 新增上下文配置**

```python
# Settings 类新增
max_context_tokens: int = 8000
max_messages_count: int = 50
```

- [ ] **Step 7: Commit**

```bash
git add browsepilot/backend/app/agent/state.py \
        browsepilot/backend/app/agent/nodes.py \
        browsepilot/backend/app/agent/tools.py \
        browsepilot/backend/app/main.py \
        browsepilot/backend/app/config.py
git commit -m "feat: add full token tracking, context compression, and fix three defects"
```

---

## 实施顺序依赖

```
Phase 1 (B+C):
Task 1 (config) ──→ Task 2 (MCP transport) ──→ Task 3 (BrowserPool) ──→ Task 4 (cleanup)
                         │                           │
                         └───────────┬───────────────┘
                                     │
Phase 2 (A):                        ↓
Task 5 (model config) ──→ Task 6 (JSON robustness)
                                     │
                                     ↓
                              Task 7 (classify)
                                     │
                                     ↓
                              Task 8 (execute retry)
                                     │
                                     ↓
                              Task 9 (node optimization)
                                     │
                                     ↓
                              Task 10 (robustness)
                                     │
                                     ↓
                              Task 11 (token tracking)
```

**关键依赖**：
- Task 5 依赖 Task 1（共享 config.py 改动）
- Task 7 依赖 Task 5（classify 需要 get_small_llm）+ Task 2（MCPClient transport 接口）
- Task 10 依赖 Task 3（MCP 超时联动）+ Task 9（reflect/replan 节点是熔断注入点）
- Task 11 依赖 Task 6（parse_llm_json 返回 usage）+ Task 9（buid_context_with_budget 使用者）

## 沟通约定

在 Task 9（节点优化）和 Task 10（健壮性）中标注了多个 **沟通点**。这些点的代码设计细节在规范中未完全确定，实施时需与用户对齐后再编码。

所有未标注沟通点的步骤，代码已在规范中明确给出，可直接按步骤实施。
