"""Execute script tool — run limited safe JavaScript."""

from browser_mcp.tools import filter_js_script


async def execute_script(browser, script: str) -> dict:
    is_safe, error = filter_js_script(script)
    if not is_safe:
        return {"status": "error", "error": error, "result": None}
    page = await browser.get_page()
    try:
        result = await page.evaluate(script)
        return {"status": "success", "result": str(result)}
    except Exception as e:
        return {"status": "error", "error": str(e), "result": None}
