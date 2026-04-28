"""Get content tool — extract page text or HTML."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def get_content(ctx: Context, format: str = "text") -> dict:
    """Extract page content as text or HTML."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    try:
        if format == "html":
            content = await page.content()
        else:
            content = await page.inner_text("body")
        screenshot = await browser.screenshot()
        return {"status": "success", "content": content[:10000], "screenshot_base64": screenshot}
    except Exception as e:
        return {"status": "error", "error": str(e), "content": ""}
