"""MCP tool implementations for browser automation."""

from urllib.parse import urlparse

ALLOWED_DOMAINS: list[str] = []


def set_allowed_domains(domains: list[str]) -> None:
    global ALLOWED_DOMAINS
    ALLOWED_DOMAINS = domains


def validate_url(url: str) -> tuple:
    """Validate URL against security policy. Returns (is_valid, error_message)."""
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


def filter_js_script(script: str) -> tuple:
    """Validate JS script safety. Returns (is_safe, error_message)."""
    blocked = ["eval", "fetch", "XMLHttpRequest", "WebSocket", "localStorage", "sessionStorage"]
    for keyword in blocked:
        if keyword in script:
            return False, f"script_blocked: '{keyword}' is not allowed"
    return True, ""


def register_all_tools(server, browser) -> None:
    """Register all MCP tools on the server. Tools will be added in Task 1.3."""
    pass  # placeholder — actual tools registered in Task 1.3
