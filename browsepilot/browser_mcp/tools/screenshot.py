"""Screenshot tool — take a full page screenshot."""


async def screenshot(browser, full_page: bool = True) -> dict:
    try:
        data = await browser.screenshot(full_page=full_page)
        if not data:
            return {"status": "error", "error": "screenshot_failed", "screenshot_base64": ""}
        return {"status": "success", "screenshot_base64": data}
    except Exception as e:
        return {"status": "error", "error": str(e), "screenshot_base64": ""}
