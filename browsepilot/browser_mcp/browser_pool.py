"""Browser instance pool with pre-warming, lifecycle, and health checks."""

import asyncio
import time
from dataclasses import dataclass, field

from loguru import logger

from browser_mcp.browser_manager import BrowserManager


@dataclass
class PooledBrowser:
    browser_manager: BrowserManager
    created_at: float = field(default_factory=time.time)
    request_count: int = 0
    last_used: float = field(default_factory=time.time)
    is_healthy: bool = True


class BrowserPoolExhausted(Exception):
    """Raised when no browser instance is available within the timeout."""
    pass


class BrowserPool:
    def __init__(
        self,
        max_size: int = 8,
        prewarm: int = 2,
        max_age_minutes: int = 30,
        max_requests: int = 50,
        idle_timeout_minutes: int = 10,
        acquire_timeout: float = 30.0,
        headless: bool = True,
        channel: str | None = None,
        browser_timeout: int = 15000,
    ):
        self.max_size = max_size
        self.prewarm = prewarm
        self.max_age_seconds = max_age_minutes * 60
        self.max_requests = max_requests
        self.idle_timeout_seconds = idle_timeout_minutes * 60
        self.acquire_timeout = acquire_timeout
        self.headless = headless
        self.channel = channel
        self.browser_timeout = browser_timeout

        self._available: asyncio.Queue[PooledBrowser] = asyncio.Queue(max_size)
        self._semaphore = asyncio.Semaphore(max_size)
        self._all_instances: set[PooledBrowser] = set()
        self._prewarmed = False

    async def start(self):
        """Pre-warm the pool with initial instances."""
        logger.info("Starting BrowserPool: pre-warming {} instances", self.prewarm)
        for _ in range(self.prewarm):
            pooled = await self._create_instance()
            self._available.put_nowait(pooled)
        self._prewarmed = True

    async def _create_instance(self) -> PooledBrowser:
        browser = BrowserManager(
            headless=self.headless,
            timeout=self.browser_timeout,
            channel=self.channel,
        )
        await browser.start()
        pooled = PooledBrowser(browser_manager=browser)
        self._all_instances.add(pooled)
        return pooled

    async def acquire(self) -> PooledBrowser:
        # Lazy pre-warm on first call
        if not self._prewarmed:
            await self.start()

        # Try non-blocking get first
        try:
            pooled = self._available.get_nowait()
            if self._is_usable(pooled):
                pooled.request_count += 1
                pooled.last_used = time.time()
                return pooled
            else:
                await self._destroy_instance(pooled)
        except asyncio.QueueEmpty:
            pass

        # Try to create new instance if under max
        if not self._semaphore.locked():
            async with self._semaphore:
                pooled = await self._create_instance()
                pooled.request_count = 1
                pooled.last_used = time.time()
                return pooled

        # Pool full: wait in queue
        try:
            pooled = await asyncio.wait_for(
                self._available.get(), timeout=self.acquire_timeout
            )
            if self._is_usable(pooled):
                pooled.request_count += 1
                pooled.last_used = time.time()
                return pooled
            else:
                await self._destroy_instance(pooled)
                raise BrowserPoolExhausted("No healthy instance available")
        except asyncio.TimeoutError:
            raise BrowserPoolExhausted(
                f"No browser available within {self.acquire_timeout}s"
            )

    async def release(self, pooled: PooledBrowser):
        if pooled not in self._all_instances:
            return
        try:
            await pooled.browser_manager.get_page()
            pooled.is_healthy = True
        except Exception as e:
            logger.warning("Browser health check failed: {}", e)
            pooled.is_healthy = False

        if not pooled.is_healthy:
            await self._destroy_instance(pooled)
            if len(self._all_instances) < self.max_size:
                new_instance = await self._create_instance()
                self._available.put_nowait(new_instance)
            return

        age = time.time() - pooled.created_at
        if age > self.max_age_seconds or pooled.request_count >= self.max_requests:
            logger.info("Browser instance reached lifecycle limit, destroying")
            await self._destroy_instance(pooled)
            return

        await pooled.browser_manager.reset()
        self._available.put_nowait(pooled)

    def _is_usable(self, pooled: PooledBrowser) -> bool:
        if not pooled.is_healthy:
            return False
        if time.time() - pooled.created_at > self.max_age_seconds:
            return False
        if pooled.request_count >= self.max_requests:
            return False
        return True

    async def _destroy_instance(self, pooled: PooledBrowser):
        if pooled in self._all_instances:
            self._all_instances.discard(pooled)
        try:
            await pooled.browser_manager.stop()
        except Exception as e:
            logger.warning("Error stopping browser instance: {}", e)


# Module-level pool singleton, initialized by main.py
pool: BrowserPool | None = None
