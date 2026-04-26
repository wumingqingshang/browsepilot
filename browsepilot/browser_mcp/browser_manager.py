"""Playwright browser instance lifecycle management."""

import base64

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger


class BrowserManager:
    def __init__(self, headless: bool = True, timeout: int = 15000):
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> Page:
        if self._playwright is not None:
            await self.stop()
        logger.info("Starting browser instance (headless={})", self.headless)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-notifications", "--disable-popup-blocking"],
        )
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout)
        return self._page

    async def get_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            logger.warning("Page closed or missing, restarting browser")
            await self.start()
        return self._page

    async def dismiss_dialogs(self) -> None:
        page = await self.get_page()
        try:
            await page.evaluate("window.alert = () => {}; window.confirm = () => true; window.prompt = () => '';")
        except Exception as e:
            logger.warning("Failed to dismiss dialogs: {}", e)

    async def screenshot(self, full_page: bool = True) -> str:
        page = await self.get_page()
        data = await page.screenshot(full_page=full_page, type="png")
        return base64.b64encode(data).decode("utf-8")

    async def stop(self) -> None:
        logger.info("Stopping browser instance")
        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.warning("Error closing context: {}", e)
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning("Error closing browser: {}", e)
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning("Error stopping playwright: {}", e)
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
