"""Click tool — click an element by selector."""

from mcp.server.fastmcp import Context
from browser_mcp.server import mcp


@mcp.tool()
async def click(selector: str, ctx: Context) -> dict:
    """Click an element identified by a CSS selector."""
    browser = ctx.request_context.lifespan_context["browser"]
    page = await browser.get_page()
    await browser.dismiss_dialogs()
    try:
        await page.wait_for_selector(selector, timeout=5000)
        await page.click(selector)
        screenshot = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot}
    except Exception as e:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": "selector_not_found", "detail": str(e), "screenshot_base64": screenshot}
