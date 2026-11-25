"""
Sliding-window rate limiter — SRP.

Counts calls within a rolling time window and raises RuntimeError when the
configured limit is exceeded. Thread-safe via asyncio.Lock.
"""
import asyncio
import collections
import time


class RateLimiter:
    def __init__(self, limit: int, window: float = 60.0) -> None:
        self._limit = limit
        self._window = window
        self._calls: collections.deque[float] = collections.deque()
        self._lock = asyncio.Lock()

    async def check(self) -> None:
        async with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= self._window:
                self._calls.popleft()
            if len(self._calls) >= self._limit:
                raise RuntimeError(
                    f"Rate limit exceeded — maximum {self._limit} requests per "
                    f"{int(self._window)}s. Please try again later."
                )
            self._calls.append(now)
