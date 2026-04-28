"""Scroll tool — scroll the page up or down."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def scroll(ctx: Context, direction: str = "down", amount: int = 500) -> dict:
    """Scroll the page up or down by a given pixel amount."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    try:
        pixels = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {pixels})")
        screenshot_data = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot_data}
    except Exception as e:
        return {"status": "error", "error": str(e)}
