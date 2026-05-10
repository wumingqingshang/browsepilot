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
        self._all_instances: set[PooledBrowser] = set()
        self._prewarmed = False
        self._eviction_task: asyncio.Task | None = None

    async def start(self):
        """Pre-warm the pool with initial instances and start eviction task."""
        logger.info("Starting BrowserPool: pre-warming {} instances", self.prewarm)
        for _ in range(self.prewarm):
            pooled = await self._create_instance()
            await self._available.put(pooled)
        self._prewarmed = True
        self._eviction_task = asyncio.create_task(self._evict_expired())

    async def _create_instance(self) -> PooledBrowser:
        browser = BrowserManager(
            headless=self.headless,
            timeout=self.browser_timeout,
            channel=self.channel,
        )
        await browser.start()
        pooled = PooledBrowser(browser_manager=browser)
        self._all_instances.add(pooled)
        logger.debug("Browser instance created (total: {})", len(self._all_instances))
        return pooled

    async def acquire(self) -> PooledBrowser:
        # Lazy pre-warm on first call
        if not self._prewarmed:
            await self.start()

        # Loop through queue to find a healthy instance (non-blocking)
        pooled = await self._try_get_healthy()
        if pooled is not None:
            return pooled

        # Try to create new instance if under max
        if len(self._all_instances) < self.max_size:
            pooled = await self._create_instance()
            pooled.request_count = 1
            pooled.last_used = time.time()
            return pooled

        # Pool full: block on queue with timeout
        deadline = time.time() + self.acquire_timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            try:
                pooled = await asyncio.wait_for(
                    self._available.get(), timeout=max(remaining, 0.1)
                )
            except asyncio.TimeoutError:
                raise BrowserPoolExhausted(
                    f"No browser available within {self.acquire_timeout}s"
                )
            if self._is_usable(pooled):
                pooled.request_count += 1
                pooled.last_used = time.time()
                return pooled
            else:
                await self._destroy_instance(pooled)

        raise BrowserPoolExhausted(
            f"No browser available within {self.acquire_timeout}s"
        )

    async def _try_get_healthy(self) -> PooledBrowser | None:
        """Non-blocking attempt to get a healthy instance from queue."""
        while True:
            try:
                pooled = self._available.get_nowait()
            except asyncio.QueueEmpty:
                return None
            if self._is_usable(pooled):
                pooled.request_count += 1
                pooled.last_used = time.time()
                return pooled
            else:
                await self._destroy_instance(pooled)

    async def release(self, pooled: PooledBrowser):
        if pooled not in self._all_instances:
            return

        # Lightweight health check: quick page evaluate, no browser restart
        pooled.is_healthy = await pooled.browser_manager.is_page_alive()
        if not pooled.is_healthy:
            logger.warning("Browser health check failed")

        if not pooled.is_healthy:
            await self._destroy_instance(pooled)
            if len(self._all_instances) < self.max_size:
                new_instance = await self._create_instance()
                await self._available.put(new_instance)
            return

        # Check lifecycle limits
        age = time.time() - pooled.created_at
        if age > self.max_age_seconds or pooled.request_count >= self.max_requests:
            logger.info("Browser instance reached lifecycle limit, destroying")
            await self._destroy_instance(pooled)
            return

        # Check idle timeout
        idle_time = time.time() - pooled.last_used
        if idle_time > self.idle_timeout_seconds:
            logger.info("Browser instance idle for {}s, destroying", int(idle_time))
            await self._destroy_instance(pooled)
            return

        # Reset and return to pool
        await pooled.browser_manager.reset()
        await self._available.put(pooled)

    def _is_usable(self, pooled: PooledBrowser) -> bool:
        if not pooled.is_healthy:
            return False
        if time.time() - pooled.created_at > self.max_age_seconds:
            return False
        if pooled.request_count >= self.max_requests:
            return False
        if time.time() - pooled.last_used > self.idle_timeout_seconds:
            return False
        return True

    async def _destroy_instance(self, pooled: PooledBrowser):
        if pooled in self._all_instances:
            self._all_instances.discard(pooled)
        try:
            await pooled.browser_manager.stop()
        except Exception as e:
            logger.warning("Error stopping browser instance: {}", e)

    async def _evict_expired(self):
        """Background task: periodically evict idle and expired instances."""
        while True:
            await asyncio.sleep(60)
            now = time.time()
            to_evict = []
            for pooled in list(self._all_instances):
                if now - pooled.last_used > self.idle_timeout_seconds:
                    to_evict.append(pooled)
                elif now - pooled.created_at > self.max_age_seconds:
                    to_evict.append(pooled)
                elif pooled.request_count >= self.max_requests:
                    to_evict.append(pooled)
            for pooled in to_evict:
                if pooled in self._all_instances:
                    logger.info("Evicting expired browser instance")
                    await self._destroy_instance(pooled)


# Module-level pool singleton, initialized by main.py
pool: BrowserPool | None = None
