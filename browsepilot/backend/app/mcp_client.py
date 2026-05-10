"""MCP client — connects to browser-mcp and discovers tools using transport abstraction."""

import json
from typing import Any

from loguru import logger
from mcp import ClientSession

from backend.app.mcp_transport import create_transport


class MCPClient:
    def __init__(self, server_config: dict | None = None):
        self.server_config = server_config or {
            "type": "streamable-http",
            "url": "http://localhost:8090/mcp",
        }
        self._transport = create_transport(self.server_config)
        self._session: ClientSession | None = None
        self._streams = None
        self._tools: list[dict] = []

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def connect(self) -> list[dict]:
        """Connect to MCP server via transport abstraction and discover available tools."""
        logger.info("Connecting to MCP server via {} transport", self.server_config.get("type", "unknown"))
        read, write = await self._transport.connect()
        self._streams = (read, write)
        try:
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
        except Exception:
            await self._transport.close()
            raise
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
            self._session = None
        if self._transport:
            await self._transport.close()
        logger.info("MCP client disconnected")
