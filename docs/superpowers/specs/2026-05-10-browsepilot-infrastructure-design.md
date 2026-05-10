# BrowsePilot 基础设施与运维保障 — 实现规范

## 概述

本规范覆盖 B+C 层 4 项需求：配置加载显式化（#9）、MCP 配置改造（#1）、BrowserPool 与资源管理（#5）、数据清理机制（#6）。

**设计约束**：5-10 并发规模，小团队内部使用，streamable-http 传输，BrowserPool 在 browser_mcp 侧，60min TTL + 100 会话上限。

---

## 一、配置加载显式化（#9）

### 1.1 显式加载

`config.py` 模块顶部显式调用 `load_dotenv()`，替代完全依赖 pydantic-settings 隐式行为：

```python
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    logger.warning(".env not found at {}", ENV_PATH)
```

### 1.2 启动时关键字段校验

```python
from pydantic import model_validator

class Settings(BaseSettings):
    @model_validator(mode="after")
    def check_critical(self):
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required. Set in .env or environment.")
        return self
```

校验在 Settings 实例化时触发，api_key 为空则服务启动即失败（fail-fast）。

### 1.3 env_file 双重保险

保留 pydantic-settings 的 `Config.env_file` 作为兜底，路径改为 `${PROJECT_ROOT}/.env`。同时 `browsepilot/.gitignore` 增加 `.env` 规则。

### 1.4 改动清单

| 文件 | 改动 | 量 |
|------|------|----|
| `browsepilot/backend/app/config.py` | 显式 load_dotenv + model_validator | ~20行 |
| `browsepilot/.gitignore` | 增加 `.env` 规则 | +1行 |

---

## 二、MCP 配置改造（#1）

### 2.1 mcp_settings.json — 统一配置入口

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

路径：`browsepilot/mcp_settings.json`。`.env` 中移除 `MCP_SERVER_URL`、`MCP_SERVER_PORT`、`MCP_MODE`。

### 2.2 传输抽象层：`backend/app/mcp_transport.py`（新建）

```
MCPTransport (ABC)
├── StreamableHTTPTransport  ← 本期完整实现
└── StdioTransport           ← 本期仅接口骨架
```

工厂函数：

```python
def create_transport(config: dict) -> MCPTransport:
    transport_type = config.get("type", "streamable-http")
    if transport_type == "streamable-http":
        return StreamableHTTPTransport(url=config["url"])
    if transport_type == "stdio":
        return StdioTransport(command=config["command"], args=config.get("args", []))
    raise ValueError(f"Unknown transport type: {transport_type}")
```

### 2.3 MCPClient 适配

- 构造函数从 `__init__(self, server_url: str)` 改为 `__init__(self, server_config: dict)`
- `connect()` 中 `sse_client(url)` → `create_transport(server_config).connect()`
- `close()` 委托给 transport

### 2.4 browser-mcp 侧：SSE → Streamable HTTP

`browser_mcp/main.py` 一行改动：`mcp.run(transport="streamable-http")`

URL 从 `http://localhost:8090/sse` 变为 `http://localhost:8090/mcp`。

### 2.5 Config 集成

新增 `load_mcp_servers()` 函数读取 `mcp_settings.json`，返回 `dict[str, dict]`。MCPClient 初始化时传入对应 server 的配置。

### 2.6 改动清单

| 文件 | 改动 | 量 |
|------|------|----|
| `browser_mcp/main.py` | `mcp.run(transport="streamable-http")` | 1行 |
| `backend/app/mcp_transport.py` | **新建** 传输抽象层 | ~70行 |
| `backend/app/mcp_client.py` | sse_client → transport 工厂，构造函数参数变更 | ~15行 |
| `backend/app/config.py` | 新增 load_mcp_servers()，移除 MCP env 变量 | ~20行 |
| `mcp_settings.json` | **新建** MCP 服务目录 | 新文件 |
| `.env.example` / `.env` | 移除 MCP_SERVER_URL/PORT/MODE | -4行 |

---

## 三、BrowserPool 与资源管理（#5）

### 3.1 BrowserPool：`browser_mcp/browser_pool.py`（新建）

核心数据结构：

```python
@dataclass
class PooledBrowser:
    browser_manager: BrowserManager
    created_at: float
    request_count: int
    last_used: float
    is_healthy: bool

class BrowserPool:
    def __init__(self, max_size=8, prewarm=2, max_age_minutes=30,
                 max_requests=50, idle_timeout_minutes=10, acquire_timeout=30.0):
        self._available = asyncio.Queue(max_size)
        self._semaphore = asyncio.Semaphore(max_size)
        ...
```

**获取流程**：
1. 尝试从 `_available` 队列获取（非阻塞）
2. 队列空 → 检查 semaphore 是否还有容量 → 有则创建新实例 → 无则 `asyncio.wait_for(_available.get(), timeout)`
3. 超时 → 抛 `BrowserPoolExhausted` 异常

**归还流程**：
1. 健康检查（浏览器进程存活）
2. 通过 → 检查是否超龄/超次 → 销毁或 `browser_manager.reset()` 后回池
3. 失败 → 销毁 + 创建新实例补充

**驱逐后台任务**：定期扫描 `_all_instances`，清理超龄、超次、空闲超时的实例。

**初始化策略**：BrowserPool 采用懒启动。`acquire()` 首次被调用时检查是否已预热，若未预热则创建 `prewarm` 个实例。这避免了 `mcp.run()`（同步）之前无法调用 `await pool.start()` 的问题。Pool 作为 `server.py` 模块级单例：

```python
# server.py
pool = BrowserPool(
    max_size=int(os.getenv("BROWSER_POOL_SIZE", "8")),
    prewarm=int(os.getenv("BROWSER_POOL_PREWARM", "2")),
    ...
)
```

### 3.2 BrowserManager 新增 reset()

```python
async def reset(self) -> None:
    """重置页面状态用于实例复用。关闭所有页面，保留浏览器实例。"""
    if self._context:
        for page in self._context.pages[1:]:
            await page.close()
        if self._context.pages:
            self._page = self._context.pages[0]
            await self._page.goto("about:blank")
```

### 3.3 Server lifespan 改造

```python
@asynccontextmanager
async def browser_lifespan(server):
    pooled = await pool.acquire()
    try:
        yield {"browser": pooled.browser_manager}
    finally:
        await pool.release(pooled)
```

### 3.4 MCPClient 加固

| 功能 | 实现 | 参数 |
|------|------|------|
| 连接重试 | `asyncio.sleep(2 ** attempt)` 指数退避 | 最多 3 次 |
| 调用超时 | `asyncio.wait_for(call_tool, timeout)` | 30s |
| 健康检查 | 连接前 `list_tools()` 快检 | — |

### 3.5 SessionManager 并发限制

`create_session()` 中检查活跃会话数，超过 `MAX_ACTIVE_SESSIONS`（默认 10）返回 HTTP 429。

### 3.6 配置项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BROWSER_POOL_SIZE` | 8 | 池最大实例数 |
| `BROWSER_POOL_PREWARM` | 2 | 预热实例数 |
| `BROWSER_MAX_AGE_MINUTES` | 30 | 单实例最大存活时间 |
| `BROWSER_MAX_REQUESTS` | 50 | 单实例最大请求数 |
| `BROWSER_IDLE_TIMEOUT` | 10 | 空闲回收（分钟） |
| `BROWSER_ACQUIRE_TIMEOUT` | 30 | 获取等待超时（秒） |
| `MCP_TOOL_TIMEOUT` | 30 | 单次工具调用超时（秒） |
| `MCP_CONNECT_RETRIES` | 3 | 连接重试次数 |
| `MAX_ACTIVE_SESSIONS` | 10 | 最大活跃会话数 |

### 3.7 改动清单

| 文件 | 改动 | 量 |
|------|------|----|
| `browser_mcp/browser_pool.py` | **新建** BrowserPool | ~150行 |
| `browser_mcp/browser_manager.py` | 新增 reset() 方法 | ~15行 |
| `browser_mcp/server.py` | lifespan 从池获取 | ~10行 |
| `browser_mcp/main.py` | 启动时初始化 BrowserPool | ~5行 |
| `backend/app/mcp_client.py` | 重试 + 超时 + 健康检查 | ~30行 |
| `backend/app/session_manager.py` | 会话数限制 | ~10行 |
| `backend/app/config.py` | 新增配置项 | ~15行 |
| `.env.example` | 新增环境变量 | +9行 |

---

## 四、数据清理机制（#6）

### 4.1 策略一：TTL 过期清理（改造 schedule_cleanup）

`schedule_cleanup` 在现有内存清理基础上，增加磁盘文件删除：

```python
def _delete_session_files(self, session_id: str):
    """删除会话 JSON + 全部关联截图 + 空目录。"""
    # 1. 读取 session JSON，遍历 execution_log
    # 2. 删除每个 step 的 screenshot_path
    # 3. 删除 session JSON 文件
    # 4. 若截图目录为空 → 删除目录
```

### 4.2 策略二：启动扫描 + 定时清理

`cleanup_on_startup()`：
- 扫描 `data/sessions/*.json`，按 mtime 排序
- 超过 `MAX_SESSIONS_COUNT` 的最旧会话 → 调用 `_delete_session_files` 删除
- `_cleanup_orphan_screenshots()`：遍历 `data/screenshots/`，无对应 session 的截图文件删除

定时清理：通过 `asyncio.create_task` 每 `CLEANUP_INTERVAL_HOURS` 小时执行一次。

### 4.3 策略三：截图写入前空间检查

`execute_node` 保存截图前调用 `check_storage_before_write()`：
- 计算 `data/` 目录总大小
- 超过 `MAX_STORAGE_MB` → 紧急清理最旧 20% 会话
- 仍不足 → 跳过截图保存，记录警告日志

### 4.4 配置项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SESSION_TTL_MINUTES` | 60 | 已有，保持不变 |
| `MAX_SESSIONS_COUNT` | 100 | 最大保留会话数 |
| `MAX_STORAGE_MB` | 500 | data/ 最大占用空间 |
| `CLEANUP_INTERVAL_HOURS` | 6 | 定时清理间隔 |

### 4.5 改动清单

| 文件 | 改动 | 量 |
|------|------|----|
| `backend/app/session_manager.py` | 磁盘清理 + 启动扫描 + 空间检查 | ~80行 |
| `backend/app/agent/nodes.py` | 截图保存前空间检查 | ~5行 |
| `backend/app/config.py` | 新增配置项 | ~5行 |

---

## 五、文件总览

```
browsepilot/
├── mcp_settings.json              ← 新建: MCP 服务目录
├── .env                           ← 移除 MCP 变量
├── .env.example                   ← 移除 MCP 变量 + 新增 Pool 配置
├── .gitignore                     ← 新增 .env 规则
├── backend/app/
│   ├── config.py                  ← 改动: 显式加载 + 校验 + MCP读取 + 新配置项
│   ├── mcp_transport.py           ← 新建: 传输抽象层
│   ├── mcp_client.py              ← 改动: transport 适配 + 加固
│   ├── session_manager.py         ← 改动: 清理 + 并发限制
│   └── agent/nodes.py             ← 改动: 截图前空间检查
└── browser_mcp/
    ├── main.py                    ← 改动: streamable-http + Pool 初始化
    ├── server.py                  ← 改动: lifespan 从池获取
    ├── browser_pool.py            ← 新建: BrowserPool
    └── browser_manager.py         ← 改动: +reset()
```

## 六、风险与注意事项

1. **streamable_http_client API 兼容性**：需验证 `mcp>=1.25.0` 的 `streamable_http_client` 上下文管理器接口与 `sse_client` 是否一致，特别是 `__aenter__` 返回的 `(read, write)` 元组

2. **BrowserPool 实例泄漏**：归还流程的 `finally` 必须覆盖所有异常路径，否则实例只借不还，池很快耗尽

3. **reset() 方法完整性**：回收浏览器实例前需确保 cookies、localStorage、service worker 等清理干净，避免会话间数据串扰

4. **文件删除并发安全**：清理任务与 `persist()` 可能并发操作同一 session 文件，需加简单文件锁或 try/except 容错

5. **StdioTransport 本期不连调**：仅实现接口骨架，无实际 MCP server 验证。未来启用时需要额外调试

6. **browser_mcp 侧 load_dotenv 独立存在**：`browser_mcp/main.py` 和 `server.py` 中的 `load_dotenv` 调用保持不变，与 backend 侧的 `config.py` 显式加载互不干扰。两边的 .env 文件是同一个（`browsepilot/.env`），但加载机制独立
