"""browser-mcp MCP Server — SSE + stdio dual-mode entry point."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount

# Load .env from project root (browsepilot/)
load_dotenv()

from browser_mcp.browser_manager import BrowserManager
from browser_mcp.tools import set_allowed_domains, register_all_tools

browser = BrowserManager(
    headless=os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
    timeout=int(os.getenv("BROWSER_TIMEOUT", "15000")),
)
mcp_server = Server("browser-mcp")
register_all_tools(mcp_server, browser)


async def run_sse():
    """Run MCP server in SSE mode."""
    port = int(os.getenv("MCP_SERVER_PORT", "8090"))
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
    import uvicorn

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    logger.info("browser-mcp SSE server starting on port {}", port)
    await server.serve()


async def run_stdio():
    """Run MCP server in stdio mode."""
    logger.info("browser-mcp stdio server starting")
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream, write_stream, mcp_server.create_initialization_options()
        )


async def main():
    domains = os.getenv("ALLOWED_DOMAINS", "")
    if domains:
        set_allowed_domains([d.strip() for d in domains.split(",")])

    mode = os.getenv("MCP_MODE", "sse").lower()

    try:
        await browser.start()
        if mode == "stdio":
            await run_stdio()
        else:
            await run_sse()
    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
