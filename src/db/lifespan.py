"""
Server lifecycle (SRP).

ConnectionPool — manages the aiomysql pool lifecycle.
AppContext     — provides access to repositories via the managed pool.
IAppContext    — Protocol that defines the AppContext contract (DIP/OCP).
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import aiomysql
from fastmcp import FastMCP

from ..config import DatabaseConfig
from .repository import SchemaRepository, QueryRepository
from .secure_repository import SecureQueryRepository

logger = logging.getLogger("mysql-mcp")


@dataclass
class ConnectionPool:
    """Single responsibility: manage the aiomysql pool lifecycle."""

    config: DatabaseConfig
    _pool: aiomysql.Pool | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def acquire(self) -> aiomysql.Pool:
        """
        Return the shared pool, creating it on the first call (double-checked locking).

        The pool is validated with ``SELECT 1`` after creation; if that probe fails,
        the pool is closed and the exception is re-raised so the caller can surface
        the connection error rather than handing back a broken pool.
        """
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is None:
                logger.info("Connecting to the MySQL cluster via Teleport proxy (lazy)...")
                pool = await aiomysql.create_pool(  # type: ignore[misc]
                    host=self.config.host,
                    port=self.config.port,
                    user=self.config.user,
                    db=None,
                    charset="utf8mb4",
                    autocommit=True,
                    minsize=self.config.pool_minsize,
                    maxsize=self.config.pool_maxsize,
                    connect_timeout=self.config.connect_timeout,
                    init_command="SET SESSION TRANSACTION READ ONLY",
                )
                try:
                    async with pool.acquire() as _conn:
                        async with _conn.cursor() as _cur:
                            await _cur.execute("SELECT 1")
                except Exception:
                    pool.close()
                    try:
                        await asyncio.wait_for(pool.wait_closed(), timeout=5)
                    except asyncio.TimeoutError:
                        logger.warning("Pool cleanup timed out during failed validation")
                    raise
                self._pool = pool
                logger.info("Connection pool created (teleport-proxy, session=read-only).")
        return self._pool

    async def close(self) -> None:
        """Close the pool gracefully; logs an error but does not raise on timeout."""
        if self._pool is not None:
            self._pool.close()
            try:
                await asyncio.wait_for(self._pool.wait_closed(), timeout=5)
                logger.info("Connection pool closed.")
            except asyncio.TimeoutError:
                logger.error("Pool shutdown timed out — forcing close")


@runtime_checkable
class IAppContext(Protocol):
    """Formal AppContext contract — allows mocking in tests without the concrete class."""

    async def get_schema_repo(self) -> SchemaRepository: ...
    async def get_query_repo(self) -> SecureQueryRepository: ...


@dataclass
class AppContext:
    """Single responsibility: provide access to repositories via the managed pool."""

    _pool: ConnectionPool
    _config: DatabaseConfig
    _schema_repo: SchemaRepository | None = field(default=None, init=False, repr=False)
    _query_repo: SecureQueryRepository | None = field(default=None, init=False, repr=False)
    _schema_init_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _query_init_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def get_schema_repo(self) -> SchemaRepository:
        """Return the singleton SchemaRepository, initialising it on the first call."""
        if self._schema_repo is not None:
            return self._schema_repo
        async with self._schema_init_lock:
            if self._schema_repo is None:
                pool = await self._pool.acquire()
                self._schema_repo = SchemaRepository(pool)
        return self._schema_repo

    async def get_query_repo(self) -> SecureQueryRepository:
        """Return the singleton SecureQueryRepository, initialising it on the first call."""
        if self._query_repo is not None:
            return self._query_repo
        async with self._query_init_lock:
            if self._query_repo is None:
                pool = await self._pool.acquire()
                inner = QueryRepository(pool, self._config.max_rows, self._config.query_timeout)
                self._query_repo = SecureQueryRepository(inner)
        return self._query_repo


@asynccontextmanager
async def build_lifespan(_server: FastMCP, *, config: DatabaseConfig):
    """Lifespan that starts without connecting to the database."""
    pool = ConnectionPool(config=config)
    ctx = AppContext(_pool=pool, _config=config)
    logger.info("Server started — MySQL connection will be made on the first request.")
    try:
        yield ctx
    finally:
        await pool.close()
