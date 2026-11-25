# tests/conftest.py
import asyncio
from unittest.mock import AsyncMock, MagicMock


def make_conn(rows=(), description=None, error=None):
    """Build a mock aiomysql conn → cursor chain.

    Args:
        rows: Iterable returned by cur.fetchall().
        description: Value for cur.description (list of (name,...) tuples or None).
        error: If set, cur.execute raises this exception.
    """
    rows_list = list(rows)
    cur = MagicMock()
    cur.fetchall = AsyncMock(return_value=rows_list)
    cur.fetchone = AsyncMock(return_value=rows_list[0] if rows_list else None)
    cur.description = description
    cur.execute = AsyncMock(side_effect=error) if error else AsyncMock()
    cur.__aenter__ = AsyncMock(return_value=cur)
    cur.__aexit__ = AsyncMock(return_value=False)

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cur)
    conn.select_db = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    return conn, cur


def make_pool(rows=(), description=None, error=None):
    """Build a mock aiomysql pool with a single conn → cursor.

    Returns (pool, conn, cur) for assertions.
    """
    conn, cur = make_conn(rows=rows, description=description, error=error)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn, cur


def make_counting_pool(rows=(), description=None, error=None):
    """Build a mock pool factory that tracks creations."""
    pool, _, _ = make_pool(rows=rows, description=description, error=error)
    counter = MagicMock()
    counter.count = 0

    async def side_effect(**_kwargs):
        counter.count += 1
        await asyncio.sleep(0)  # yield to loop
        return pool

    return side_effect, counter
