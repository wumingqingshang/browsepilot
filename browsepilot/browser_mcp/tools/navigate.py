"""Navigate tool — go to a URL."""

import asyncio
from browser_mcp.tools import validate_url


async def navigate(browser, url: str) -> dict:
    is_valid, error = validate_url(url)
    if not is_valid:
        return {"status": "error", "error": error}
    page = await browser.get_page()
    try:
        await asyncio.wait_for(page.goto(url, wait_until="domcontentloaded"), timeout=15)
        title = await page.title()
        screenshot = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot, "title": title}
    except asyncio.TimeoutError:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": "timeout", "screenshot_base64": screenshot}
    except Exception as e:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": str(e), "screenshot_base64": screenshot}
