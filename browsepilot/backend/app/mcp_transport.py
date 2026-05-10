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
