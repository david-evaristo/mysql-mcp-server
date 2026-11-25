# tests/test_rate_limiter.py
import time
import pytest

from src.rate_limiter import RateLimiter


class TestRateLimiter:
    async def test_single_call_within_limit_passes(self):
        rl = RateLimiter(limit=3, window=60.0)
        await rl.check()  # should not raise

    async def test_calls_at_limit_all_pass(self):
        rl = RateLimiter(limit=3, window=60.0)
        await rl.check()
        await rl.check()
        await rl.check()  # third call = at limit, still ok

    async def test_call_over_limit_raises_runtime_error(self):
        rl = RateLimiter(limit=2, window=60.0)
        await rl.check()
        await rl.check()
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await rl.check()

    async def test_calls_outside_window_are_pruned(self):
        rl = RateLimiter(limit=2, window=1.0)
        expired = time.monotonic() - 2.0
        import collections
        rl._calls = collections.deque([expired, expired])

        await rl.check()  # both old calls pruned; counter = 1, under limit
        assert len(rl._calls) == 1  # verify pruning occurred and new call recorded

    async def test_error_message_includes_limit_and_window(self):
        rl = RateLimiter(limit=1, window=30.0)
        await rl.check()
        with pytest.raises(RuntimeError, match="1") as exc_info:
            await rl.check()
        assert "30" in str(exc_info.value)
