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


def register_all_tools(server, browser) -> None:
    """Register all browser tools via MCP low-level handlers (list_tools + call_tool)."""
    import json

    import mcp.types as types

    from browser_mcp.tools.navigate import navigate
    from browser_mcp.tools.click import click
    from browser_mcp.tools.type_text import type_text
    from browser_mcp.tools.get_content import get_content
    from browser_mcp.tools.screenshot import screenshot as screenshot_tool
    from browser_mcp.tools.scroll import scroll
    from browser_mcp.tools.execute_script import execute_script
    from browser_mcp.tools.get_page_structure import get_page_structure

    TOOL_HANDLERS = {
        "navigate": {"func": navigate, "schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
        "click": {"func": click, "schema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
        "type_text": {"func": type_text, "schema": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]}},
        "get_content": {"func": get_content, "schema": {"type": "object", "properties": {"format": {"type": "string", "default": "text"}}}},
        "screenshot": {"func": screenshot_tool, "schema": {"type": "object", "properties": {"full_page": {"type": "boolean", "default": True}}}},
        "scroll": {"func": scroll, "schema": {"type": "object", "properties": {"direction": {"type": "string", "default": "down"}, "amount": {"type": "integer", "default": 500}}}},
        "execute_script": {"func": execute_script, "schema": {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]}},
        "get_page_structure": {"func": get_page_structure, "schema": {"type": "object", "properties": {}, "required": []}},
    }

    @server.list_tools()
    async def handle_list_tools(request: types.ListToolsRequest) -> list[types.Tool]:
        return [
            types.Tool(
                name=name,
                description=info["func"].__doc__ or "",
                inputSchema=info["schema"],
            )
            for name, info in TOOL_HANDLERS.items()
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict | None
    ) -> list[types.TextContent]:
        args = arguments or {}
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return [types.TextContent(type="text", text=json.dumps({"status": "error", "error": f"unknown tool: {name}"}, ensure_ascii=False))]
        result = await handler["func"](browser, **args)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
