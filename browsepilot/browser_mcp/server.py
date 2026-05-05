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
    channel = os.getenv("BROWSER_CHANNEL", "") or None
    browser = BrowserManager(headless=headless, timeout=timeout, channel=channel)
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
