"""Click tool — click an element by selector."""


async def click(browser, selector: str) -> dict:
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
