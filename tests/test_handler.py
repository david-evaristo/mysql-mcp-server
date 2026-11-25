# tests/test_handler.py
import logging
import pytest

from src.handler import run_tool
from src.db.exceptions import DatabaseError

_log = logging.getLogger("test")


class TestRunTool:
    async def test_returns_value_on_success(self):
        async def _coro():
            return 42

        result = await run_tool("op", _coro(), _log)
        assert result == 42

    async def test_value_error_is_reraised(self):
        async def _coro():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await run_tool("op", _coro(), _log)

    async def test_database_error_raises_runtime_error(self):
        async def _coro():
            raise DatabaseError("db down")

        with pytest.raises(RuntimeError, match="Error accessing the database"):
            await run_tool("op", _coro(), _log)

    async def test_database_error_is_chained(self):
        original = DatabaseError("db down")

        async def _coro():
            raise original

        with pytest.raises(RuntimeError) as exc_info:
            await run_tool("op", _coro(), _log)

        assert exc_info.value.__cause__ is original


class TestRunToolRateLimit:
    @pytest.fixture(autouse=True)
    def reset_rate_limiter(self):
        import src.handler as _handler
        _handler.reset_rate_limiter()
        yield
        _handler.reset_rate_limiter()

    async def test_no_rate_limiter_configured_passes(self):
        async def _coro():
            return 99

        result = await run_tool("op", _coro(), _log)
        assert result == 99

    async def test_call_within_rate_limit_passes(self):
        from src.rate_limiter import RateLimiter
        import src.handler as _handler
        _handler.configure_rate_limiter(RateLimiter(limit=5, window=60.0))

        async def _coro():
            return "ok"

        result = await run_tool("op", _coro(), _log)
        assert result == "ok"

    async def test_call_over_rate_limit_raises_runtime_error(self):
        from src.rate_limiter import RateLimiter
        import src.handler as _handler
        _handler.configure_rate_limiter(RateLimiter(limit=1, window=60.0))

        async def _coro():
            return "ok"

        await run_tool("op", _coro(), _log)  # first: ok
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await run_tool("op", _coro(), _log)  # second: blocked

    async def test_coroutine_not_executed_when_rate_limited(self):
        from src.rate_limiter import RateLimiter
        import src.handler as _handler
        _handler.configure_rate_limiter(RateLimiter(limit=1, window=60.0))

        executed = []

        async def _coro():
            executed.append(1)
            return "ok"

        await run_tool("op", _coro(), _log)  # first: executes
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await run_tool("op", _coro(), _log)  # second: blocked before body runs

        assert len(executed) == 1
