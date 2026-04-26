"""Get content tool — extract page text or HTML."""


async def get_content(browser, format: str = "text") -> dict:
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
