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
    from browser_mcp.tools.navigate import navigate
    from browser_mcp.tools.click import click
    from browser_mcp.tools.type_text import type_text
    from browser_mcp.tools.get_content import get_content
    from browser_mcp.tools.screenshot import screenshot as screenshot_tool
    from browser_mcp.tools.scroll import scroll
    from browser_mcp.tools.execute_script import execute_script

    @server.tool()
    async def tool_navigate(url: str) -> dict:
        return await navigate(browser, url)

    @server.tool()
    async def tool_click(selector: str) -> dict:
        return await click(browser, selector)

    @server.tool()
    async def tool_type_text(selector: str, text: str) -> dict:
        return await type_text(browser, selector, text)

    @server.tool()
    async def tool_get_content(format: str = "text") -> dict:
        return await get_content(browser, format)

    @server.tool()
    async def tool_screenshot(full_page: bool = True) -> dict:
        return await screenshot_tool(browser, full_page)

    @server.tool()
    async def tool_scroll(direction: str = "down", amount: int = 500) -> dict:
        return await scroll(browser, direction, amount)

    @server.tool()
    async def tool_execute_script(script: str) -> dict:
        return await execute_script(browser, script)
