"""MCP SSE Client — connects to browser-mcp and discovers tools."""

import json
from typing import Any

from loguru import logger
from mcp import ClientSession
from mcp.client.sse import sse_client


class MCPClient:
    def __init__(self, server_url: str = "http://localhost:8090"):
        self.server_url = server_url
        self._session: ClientSession | None = None
        self._streams = None
        self._tools: list[dict] = []

    async def connect(self) -> list[dict]:
        """Connect to MCP server via SSE and discover available tools."""
        logger.info("Connecting to MCP server at {}", self.server_url)
        self._streams = sse_client(self.server_url)
        read, write = await self._streams.__aenter__()
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
        logger.info("Discovered {} tools: {}", len(self._tools), [t["name"] for t in self._tools])
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool on the MCP server and return parsed result."""
        if not self._session:
            raise RuntimeError("MCP client not connected")
        result = await self._session.call_tool(tool_name, arguments)
        if hasattr(result, "content") and result.content:
            text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"status": "success", "result": text}
        return {"status": "success", "result": str(result)}

    async def get_tools_schema(self) -> list[dict]:
        """Return tools in OpenAI function-calling format for LangChain."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"] if t["parameters"] else {"type": "object", "properties": {}},
                },
            }
            for t in self._tools
        ]

    @property
    def tools(self) -> list[dict]:
        """Return raw tool metadata list."""
        return self._tools

    async def close(self) -> None:
        """Cleanly disconnect from MCP server."""
        if self._session:
            await self._session.__aexit__(None, None, None)
        if self._streams:
            await self._streams.__aexit__(None, None, None)
        logger.info("MCP client disconnected")
