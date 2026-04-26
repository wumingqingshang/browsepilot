"""Type text tool — type into an input element."""


async def type_text(browser, selector: str, text: str) -> dict:
    page = await browser.get_page()
    await browser.dismiss_dialogs()
    try:
        await page.wait_for_selector(selector, timeout=5000)
        await page.fill(selector, text)
        screenshot = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot}
    except Exception as e:
        screenshot = await browser.screenshot()
        return {"status": "error", "error": "selector_not_found", "detail": str(e), "screenshot_base64": screenshot}
