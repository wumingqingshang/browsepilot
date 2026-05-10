"""MCP tool description helpers."""


def get_tools_description(mcp_client) -> str:
    """Generate tool description text directly from MCP tool metadata."""
    lines = []
    for t in mcp_client.tools:
        lines.append(f"- {t['name']}: {t.get('description', '')}")
    return "\n".join(lines)


async def build_tools_from_mcp(mcp_client) -> list:
    """Return tools list from MCP client. Kept for graph.py compatibility."""
    return mcp_client.tools
