"""Click tool — click an element by selector."""

import asyncio

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

        # Capture URL before click to detect navigation
        url_before = page.url

        await page.click(selector)

        # Wait for potential navigation triggered by the click
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass  # No navigation or timeout — continue anyway

        # If URL changed, wait a bit more for dynamic content
        if page.url != url_before:
            try:
                await asyncio.wait_for(page.wait_for_load_state("domcontentloaded"), timeout=3)
            except Exception:
                pass

        screenshot = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot}
    except Exception as e:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": "selector_not_found", "detail": str(e), "screenshot_base64": screenshot}
