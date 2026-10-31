import asyncio
import time

from app.mapping import Rates


class FxCache:
    """Process-local TTL cache with one shared in-flight refresh. No stale fallback."""

    def __init__(self, ttl: float):
        self.ttl = ttl
        self.value = None
        self.expires_at = 0.0
        self.inflight = None

    async def get(self, loader):
        if self.value is not None and time.monotonic() < self.expires_at:
            return self.value
        if self.inflight is None or self.inflight.done():
            self.inflight = asyncio.create_task(self._load(loader))
            self.inflight.add_done_callback(self._finished)
        task = self.inflight
        try:
            return await asyncio.shield(task)
        finally:
            if task.done() and self.inflight is task:
                self.inflight = None

    def _finished(self, task):
        # Clean up even when all callers cancelled their shielded waits.
        if self.inflight is task:
            self.inflight = None
        if not task.cancelled():
            task.exception()  # Retrieve an orphaned failure; waiters still receive it.

    async def aclose(self):
        task = self.inflight
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _load(self, loader):
        value = await loader()
        rates = Rates.model_validate(value)
        if rates.base != "USD":
            raise ValueError("Unexpected FX base")
        self.value = value
        self.expires_at = time.monotonic() + self.ttl
        return value
