# tests/test_lifespan.py
"""Tests for src/db/lifespan.py — pool lifecycle, double-checked locking, and AppContext."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from .conftest import make_counting_pool
from src.config import DatabaseConfig
from src.db.lifespan import ConnectionPool, AppContext


def _make_config() -> DatabaseConfig:
    return DatabaseConfig(host="localhost", port=54855, user="test")


class TestConnectionPoolClose:
    """``ConnectionPool.close`` drains the pool gracefully and tolerates a missing pool."""
    async def test_close_when_pool_is_none_is_noop(self):
        config = _make_config()
        cp = ConnectionPool(config=config)

        await cp.close()  # should not raise

    async def test_close_when_pool_exists_calls_wait_closed(self):
        config = _make_config()
        cp = ConnectionPool(config=config)

        mock_pool = MagicMock()
        mock_pool.wait_closed = AsyncMock()
        cp._pool = mock_pool

        await cp.close()

        mock_pool.close.assert_called_once()
        mock_pool.wait_closed.assert_called_once()

    async def test_close_completes_when_wait_closed_times_out(self):
        config = _make_config()
        cp = ConnectionPool(config=config)

        mock_pool = MagicMock()
        mock_pool.wait_closed = AsyncMock(side_effect=asyncio.TimeoutError)
        cp._pool = mock_pool

        await cp.close()  # must not raise even if wait_closed times out

        mock_pool.close.assert_called_once()


class TestConnectionPoolDoubleCheckedLocking:
    """Pool must be created exactly once even when many coroutines race to acquire it."""
    async def test_pool_created_once_under_concurrency(self):
        config = _make_config()
        cp = ConnectionPool(config=config)

        side_effect, counter = make_counting_pool()

        with patch("src.db.lifespan.aiomysql.create_pool", side_effect=side_effect):
            results = await asyncio.gather(*[cp.acquire() for _ in range(10)])

        assert counter.count == 1, f"Expected 1 pool creation, got {counter.count}"
        assert len(set(id(r) for r in results)) == 1

    async def test_acquire_fast_path_without_lock(self):
        config = _make_config()
        cp = ConnectionPool(config=config)
        cp._pool = MagicMock()
        result = await cp.acquire()
        assert result is cp._pool


class TestConnectionPoolInitCommand:
    """Pool must be created without a password and with the read-only session guard."""
    async def test_create_pool_receives_init_command(self):
        config = DatabaseConfig(host="h", port=54855, user="u")
        cp = ConnectionPool(config=config)

        side_effect, counter = make_counting_pool()
        captured = {}

        async def capturing_side_effect(**kwargs):
            captured.update(kwargs)
            return (await side_effect(**kwargs))

        with patch("src.db.lifespan.aiomysql.create_pool", side_effect=capturing_side_effect):
            await cp.acquire()

        assert captured.get("init_command") == "SET SESSION TRANSACTION READ ONLY"
        assert "password" not in captured
        assert "ssl" not in captured


class TestAppContextRaceCondition:
    """Repositories must be singletons even when initialised concurrently."""
    async def test_schema_repo_created_once_under_concurrency(self):
        config = _make_config()
        pool_mock = MagicMock()

        cp = MagicMock(spec=ConnectionPool)
        cp.acquire = AsyncMock(return_value=pool_mock)

        ctx = AppContext(_pool=cp, _config=config)
        repos = await asyncio.gather(*[ctx.get_schema_repo() for _ in range(10)])

        assert len(set(id(r) for r in repos)) == 1
        assert cp.acquire.call_count == 1
