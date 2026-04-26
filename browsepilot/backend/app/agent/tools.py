"""Convert MCP tools to LangChain Tool objects."""

from langchain_core.tools import tool


def mcp_tool_to_langchain(mcp_client, tool_info: dict):
    """Create a LangChain Tool from MCP tool metadata."""
    tool_name = tool_info["name"]

    @tool(tool_name, description=tool_info.get("description", ""))
    async def dynamic_tool(**kwargs) -> str:
        import json
        result = await mcp_client.call_tool(tool_name, kwargs)
        return json.dumps(result, ensure_ascii=False)

    return dynamic_tool


async def build_tools_from_mcp(mcp_client) -> list:
    """Build a list of LangChain Tool objects from connected MCP client."""
    langchain_tools = []
    for t in mcp_client.tools:
        lc_tool = mcp_tool_to_langchain(mcp_client, t)
        langchain_tools.append(lc_tool)
    return langchain_tools
