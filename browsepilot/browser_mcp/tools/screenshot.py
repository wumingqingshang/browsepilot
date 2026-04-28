"""Screenshot tool — take a full page screenshot."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def screenshot(ctx: Context, full_page: bool = True) -> dict:
    """Take a screenshot of the current page."""
    browser = ctx.request_context.lifespan_context["browser"]
    try:
        data = await browser.screenshot(full_page=full_page)
        if not data:
            return {"status": "error", "error": "screenshot_failed", "screenshot_base64": ""}
        return {"status": "success", "screenshot_base64": data}
    except Exception as e:
        return {"status": "error", "error": str(e), "screenshot_base64": ""}
