"""Scroll tool — scroll the page up or down."""


async def scroll(browser, direction: str = "down", amount: int = 500) -> dict:
    page = await browser.get_page()
    try:
        pixels = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {pixels})")
        screenshot_data = await browser.screenshot()
        return {"status": "success", "screenshot_base64": screenshot_data}
    except Exception as e:
        return {"status": "error", "error": str(e)}
