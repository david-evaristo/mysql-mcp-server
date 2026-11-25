"""
Database access repositories (SRP / DIP).

SchemaRepository — metadata: databases, tables, columns, indexes.
TableCache       — cache of valid tables per database (SRP).
QueryRepository  — query execution and data sampling.

Tools depend on these classes, not on the aiomysql driver directly.
"""
import asyncio
import re
import time
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import aiomysql

from .exceptions import DatabaseError, QueryTimeoutError
from .query_guard import SYSTEM_DATABASES, add_limit

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")


_EXCLUDED_DATABASES_CLAUSE = (
    "TABLE_SCHEMA NOT IN ("
    + ", ".join(f"'{db}'" for db in sorted(SYSTEM_DATABASES))
    + ")"
)


def _column_names(cur) -> list[str]:
    """Return the column names of the last executed statement (empty if none)."""
    return [d[0] for d in cur.description] if cur.description else []


def _to_dicts(rows) -> list[dict]:
    """Convert driver row objects into plain dicts."""
    return [dict(r) for r in rows]


class BaseRepository:
    """Base class holding the aiomysql pool and a cursor helper (SRP)."""
    def __init__(self, pool: aiomysql.Pool) -> None:
        """Store the shared connection pool."""
        self._pool = pool

    def _cursor(self, cursor_class: type = aiomysql.DictCursor) -> AbstractAsyncContextManager[aiomysql.Cursor]:
        """
        Build an async context manager that yields a cursor on a pooled connection.

        Args:
            cursor_class: aiomysql cursor type (``DictCursor`` by default).
        """
        @asynccontextmanager
        async def _ctx() -> AsyncIterator[aiomysql.Cursor]:
            """Acquire a connection, open a cursor, and yield it."""
            async with self._pool.acquire() as conn, conn.cursor(cursor_class) as cur:
                yield cur
        return _ctx()


class SchemaRepository(BaseRepository):
    """Single responsibility: schema metadata queries."""

    async def list_databases(self) -> list[str]:
        """
        List the user databases, excluding system schemas.

        Returns:
            Sorted database names.

        Raises:
            DatabaseError: The driver failed while listing databases.
        """
        try:
            async with self._cursor(aiomysql.Cursor) as cur:
                await cur.execute("SHOW DATABASES")
                rows = await cur.fetchall()  # type: ignore[misc]
        except aiomysql.Error as exc:
            raise DatabaseError("Failed to list databases.") from exc
        return sorted(r[0] for r in rows if r[0].lower() not in SYSTEM_DATABASES)

    async def list_tables(self, database: str) -> list[dict]:
        """
        List the tables of a database with approximate size metadata.

        Args:
            database: Database (schema) name.

        Returns:
            One dict per table (name, type, approx. rows, size in MB, timestamps).

        Raises:
            ValueError:    The database does not exist or has no tables.
            DatabaseError: The driver failed while listing tables.
        """
        sql = """
            SELECT
                TABLE_NAME        AS table_name,
                TABLE_TYPE        AS table_type,
                TABLE_ROWS        AS approx_rows,
                ROUND(DATA_LENGTH / 1024 / 1024, 2) AS size_mb,
                CREATE_TIME       AS created_at,
                UPDATE_TIME       AS updated_at
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME
        """
        try:
            async with self._cursor() as cur:
                # 1. Primeiro checa se o database existe
                await cur.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (database,))
                if not await cur.fetchone():
                    raise ValueError(f"Database '{database}' not found.")

                # 2. Busca as tabelas
                await cur.execute(sql, (database,))
                rows = await cur.fetchall()  # type: ignore[misc]
        except aiomysql.Error as exc:
            raise DatabaseError(f"Failed to list tables for '{database}'.") from exc

        if not rows:
            raise ValueError(f"Database '{database}' exists but has no tables.")

        return _to_dicts(rows)

    async def describe_table(self, database: str, table: str) -> dict:
        """
        Return the columns and indexes of a table.

        Both queries run sequentially on a single connection: opening a second
        concurrent connection can be rejected by Teleport auto user provisioning
        ("roles for user ... has changed") while another session is active.

        Args:
            database: Database (schema) name.
            table:    Table name.

        Returns:
            ``{"database", "table", "columns", "indexes"}``.

        Raises:
            ValueError:    The table does not exist (no columns found).
            DatabaseError: The driver failed while querying the metadata.
        """
        try:
            async with self._cursor() as cur:
                await cur.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
                           COLUMN_KEY, COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (database, table),
                )
                columns = _to_dicts(await cur.fetchall())  # type: ignore[misc]
                if not columns:
                    raise ValueError(f"Table '{database}.{table}' not found.")

                await cur.execute(
                    """
                    SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY INDEX_NAME, SEQ_IN_INDEX
                    """,
                    (database, table),
                )
                indexes = _to_dicts(await cur.fetchall())  # type: ignore[misc]
        except aiomysql.Error as exc:
            raise DatabaseError(f"Failed to describe table '{database}.{table}'.") from exc

        return {"database": database, "table": table, "columns": columns, "indexes": indexes}

    async def search_tables(self, pattern: str, database: str | None = None) -> list[dict]:
        """
        Search tables by name using a SQL LIKE pattern (system schemas excluded).

        Args:
            pattern:  LIKE pattern (e.g. ``%user%``).
            database: Optional database to restrict the search to.

        Returns:
            Up to 200 matches as dicts with ``database``, ``table`` and ``approx_rows``.

        Raises:
            DatabaseError: The driver failed while searching.
        """
        where = _EXCLUDED_DATABASES_CLAUSE
        params: list[Any] = []
        if database:
            where += " AND TABLE_SCHEMA = %s"
            params.append(database)
        where += " AND TABLE_NAME LIKE %s"
        params.append(pattern)

        sql = f"""
            SELECT TABLE_SCHEMA AS `database`, TABLE_NAME AS `table`,
                   TABLE_ROWS AS approx_rows
            FROM information_schema.TABLES
            WHERE {where}
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            LIMIT 200
        """
        try:
            async with self._cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()  # type: ignore[misc]
        except aiomysql.Error as exc:
            raise DatabaseError("Failed to search tables.") from exc
        return _to_dicts(rows)


_SCHEMA_TTL = 300  # seconds
_MAX_CACHED_DATABASES = 50


class TableCache(BaseRepository):
    """Single responsibility: cache of valid tables per database."""

    def __init__(self, pool: aiomysql.Pool, ttl: int = _SCHEMA_TTL) -> None:
        """
        Store the pool and initialise the per-database cache structures.

        Args:
            pool: Shared connection pool.
            ttl:  Seconds a cached table list stays valid.
        """
        super().__init__(pool)
        self._ttl = ttl
        self._cache: dict[str, set[str]] = {}
        self._expires_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, database: str) -> asyncio.Lock:
        """Return the lock for a database, creating it on first use."""
        return self._locks.setdefault(database, asyncio.Lock())

    async def get_valid_tables(self, database: str) -> set[str]:
        """
        Return the set of table names of a database, using the TTL cache.

        Concurrent misses for the same database are serialised so only one query runs.
        When the cache is full, the oldest database entry is evicted (FIFO).

        Args:
            database: Database (schema) name.

        Returns:
            Table names of the database.

        Raises:
            DatabaseError: The driver failed while fetching the table names.
        """
        now = time.monotonic()
        if now < self._expires_at.get(database, 0.0):
            return self._cache[database]                     # fast path

        async with self._get_lock(database):                 # serializa por banco
            if now < self._expires_at.get(database, 0.0):   # re-check após lock
                return self._cache[database]

            try:
                try:
                    async with self._cursor(aiomysql.Cursor) as cur:
                        await cur.execute(
                            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
                            (database,),
                        )
                        rows = await cur.fetchall()  # type: ignore[misc]

                    # Evict oldest entry (FIFO) when cache is full
                    if len(self._cache) >= _MAX_CACHED_DATABASES and database not in self._cache:
                        evicted = next(iter(self._cache))
                        del self._cache[evicted]
                        self._expires_at.pop(evicted, None)
                        self._locks.pop(evicted, None)

                    self._cache[database] = {r[0] for r in rows}
                    self._expires_at[database] = time.monotonic() + self._ttl
                    return self._cache[database]
                except aiomysql.Error as exc:
                    raise DatabaseError(f"Failed to fetch tables for database '{database}'.") from exc
            finally:
                if self._cache.get(database) is None:
                    self._locks.pop(database, None)


class QueryRepository(BaseRepository):
    """Single responsibility: query execution against the database."""

    def __init__(
        self,
        pool: aiomysql.Pool,
        max_rows: int = 500,
        query_timeout: int = 30,
    ) -> None:
        """
        Store the pool, limits and the table-name cache.

        Args:
            pool:          Shared connection pool.
            max_rows:      Hard cap on rows returned by a query.
            query_timeout: Seconds before a query is cancelled.
        """
        super().__init__(pool)
        self._max_rows = max_rows
        self._query_timeout = query_timeout
        self._table_cache = TableCache(pool)

    async def execute_query(
        self,
        sql: str,
        database: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Execute a SELECT, capping rows and detecting truncation.

        Fetches ``limit + 1`` rows so truncation is detected without a COUNT query.

        Args:
            sql:      SQL statement (already validated by the caller).
            database: Optional default database for the query.
            limit:    Requested row limit, capped at ``max_rows``.

        Returns:
            ``{"row_count", "columns", "rows", "limited"}``.

        Raises:
            QueryTimeoutError: The query exceeded the time limit.
            DatabaseError:     The driver failed while executing the query.
        """
        limit = min(limit, self._max_rows)
        sql = add_limit(sql, limit + 1)

        async def _run() -> tuple:
            """Run the query on a pooled connection and return the rows and column names."""
            async with self._pool.acquire() as conn:
                if database:
                    await conn.select_db(database)
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql)
                    _rows = await cur.fetchall()  # type: ignore[misc]
                    _col_names = _column_names(cur)
                    return _rows, _col_names

        try:
            rows, col_names = await asyncio.wait_for(_run(), timeout=self._query_timeout)
        except asyncio.TimeoutError as exc:
            raise QueryTimeoutError(f"Query exceeded the time limit of {self._query_timeout}s.") from exc
        except aiomysql.Error as exc:
            raise DatabaseError("Query execution failed.") from exc

        was_limited = len(rows) > limit
        rows = rows[:limit]

        return {
            "row_count": len(rows),
            "columns": col_names,
            "rows": _to_dicts(rows),
            "limited": was_limited,
        }

    async def get_table_sample(self, database: str, table: str, rows: int = 5) -> dict[str, Any]:
        """
        Return a small sample of rows from a table.

        Args:
            database: Database (schema) name.
            table:    Table name, validated against the table cache.
            rows:     Number of rows requested, capped at 20.

        Returns:
            ``{"database", "table", "columns", "sample_rows"}``.

        Raises:
            ValueError:        Invalid identifier or unknown table.
            QueryTimeoutError: The sample exceeded the time limit.
            DatabaseError:     The driver failed while sampling.
        """
        if not _IDENTIFIER_RE.match(database) or not _IDENTIFIER_RE.match(table):
            raise ValueError("Invalid identifier — must contain only letters, digits, underscores, or $.")
        sample_size = min(rows, 20)
        valid = await self._table_cache.get_valid_tables(database)
        if table not in valid:
            raise ValueError(f"Table '{database}.{table}' not found.")
        sql = f"SELECT * FROM `{database}`.`{table}` LIMIT {sample_size}"

        async def _run() -> tuple:
            """Run the sample query and return the rows and column names."""
            async with self._cursor() as cur:
                await cur.execute(sql)
                data_ = await cur.fetchall()  # type: ignore[misc]
                return data_, _column_names(cur)

        try:
            data, col_names = await asyncio.wait_for(_run(), timeout=self._query_timeout)
        except asyncio.TimeoutError as exc:
            raise QueryTimeoutError(
                f"Table sample exceeded the time limit of {self._query_timeout}s."
            ) from exc
        except aiomysql.Error as exc:
            raise DatabaseError(f"Failed to sample table '{database}.{table}'.") from exc
        return {
            "database": database,
            "table": table,
            "columns": col_names,
            "sample_rows": _to_dicts(data),
        }
