# tests/test_repository.py
"""Tests for src/db/repository.py — SchemaRepository, TableCache, and QueryRepository."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiomysql
import pytest

from src.db.exceptions import DatabaseError
from src.db.repository import SchemaRepository, TableCache, QueryRepository
from tests.conftest import make_pool


class TestListDatabases:
    """``list_databases`` returns only user databases, filtering out system schemas."""
    async def test_returns_sorted_user_databases(self):
        """System schemas are filtered out and the result is sorted."""
        rows = [
            ("information_schema",), ("mydb",), ("sys",),
            ("appdb",), ("performance_schema",), ("mysql",),
        ]
        pool, _, _ = make_pool(rows=rows)
        repo = SchemaRepository(pool)

        result = await repo.list_databases()

        assert result == ["appdb", "mydb"]

    async def test_aiomysql_error_raises_database_error(self):
        """Driver errors are wrapped in ``DatabaseError``."""
        pool, _, _ = make_pool(error=aiomysql.Error("conn failed"))
        repo = SchemaRepository(pool)

        with pytest.raises(DatabaseError, match="Failed to list databases"):
            await repo.list_databases()


class TestListTables:
    """``list_tables`` distinguishes between a missing database and an empty one."""
    async def test_returns_list_of_dicts(self):
        """Tables are returned as a list of dicts."""
        rows = [{"table_name": "users", "table_type": "BASE TABLE",
                 "approx_rows": 100, "size_mb": 1.5,
                 "created_at": None, "updated_at": None}]
        pool, _, cur = make_pool(rows=rows)
        # Mock fetchone para retornar o nome do banco (Database exists)
        cur.fetchone = AsyncMock(return_value={"SCHEMA_NAME": "mydb"})
        # Mock fetchall para retornar os dados da tabela
        cur.fetchall = AsyncMock(return_value=rows)
        repo = SchemaRepository(pool)

        result = await repo.list_tables("mydb")

        assert len(result) == 1
        assert result[0]["table_name"] == "users"

    async def test_database_not_found_raises_value_error(self):
        """A missing database raises ``ValueError``."""
        pool, _, cur = make_pool(rows=())
        cur.fetchone = AsyncMock(return_value=None)  # Database not found
        repo = SchemaRepository(pool)

        with pytest.raises(ValueError, match="not found"):
            await repo.list_tables("nonexistent")

    async def test_empty_database_raises_distinct_value_error(self):
        """An existing database without tables raises a distinct ``ValueError``."""
        pool, _, cur = make_pool(rows=())
        cur.fetchone = AsyncMock(return_value={"SCHEMA_NAME": "mydb"})  # Database exists
        cur.fetchall = AsyncMock(return_value=[])        # But has no tables
        repo = SchemaRepository(pool)

        with pytest.raises(ValueError, match="exists but has no tables"):
            await repo.list_tables("mydb")

    async def test_aiomysql_error_raises_database_error(self):
        """Driver errors are wrapped in ``DatabaseError``."""
        pool, _, _ = make_pool(error=aiomysql.Error("timeout"))
        repo = SchemaRepository(pool)

        with pytest.raises(DatabaseError, match="Failed to list tables"):
            await repo.list_tables("mydb")


class TestDescribeTable:
    """``describe_table`` returns columns and indexes; raises on unknown tables."""
    async def test_returns_columns_and_indexes(self):
        """Columns and indexes are returned, fetched over a single connection."""
        columns_data = [{"COLUMN_NAME": "id", "COLUMN_TYPE": "int",
                         "IS_NULLABLE": "NO", "COLUMN_KEY": "PRI",
                         "COLUMN_DEFAULT": None, "EXTRA": "", "COLUMN_COMMENT": ""}]
        indexes_data = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": "id",
                         "NON_UNIQUE": 0, "SEQ_IN_INDEX": 1}]

        pool, _, cur = make_pool()
        cur.fetchall = AsyncMock(side_effect=[columns_data, indexes_data])

        repo = SchemaRepository(pool)
        result = await repo.describe_table("mydb", "users")

        # A single connection: Teleport auto user provisioning can reject
        # concurrent connections opened for the same request.
        pool.acquire.assert_called_once()
        assert result["database"] == "mydb"
        assert result["table"] == "users"
        assert result["columns"] == columns_data
        assert result["indexes"] == indexes_data

    async def test_empty_columns_raises_value_error(self):
        """A table with no columns is reported as not found."""
        pool, _, _ = make_pool(rows=())

        repo = SchemaRepository(pool)

        with pytest.raises(ValueError, match="not found"):
            await repo.describe_table("mydb", "ghost")

    async def test_aiomysql_error_raises_database_error(self):
        """Driver errors are wrapped in ``DatabaseError``."""
        pool, _, _ = make_pool(error=aiomysql.Error("db error"))

        repo = SchemaRepository(pool)

        with pytest.raises(DatabaseError, match="Failed to describe table"):
            await repo.describe_table("mydb", "users")


class TestSearchTables:
    """``search_tables`` performs a LIKE pattern search with an optional database filter."""
    async def test_returns_matching_tables(self):
        """Matching tables are returned with database, table and approx. rows."""
        rows = [{"database": "appdb", "table": "users", "approx_rows": 50}]
        pool, _, cur = make_pool(rows=rows)
        repo = SchemaRepository(pool)

        result = await repo.search_tables("%user%")

        assert len(result) == 1
        assert result[0]["table"] == "users"

    async def test_database_filter_appended_to_params(self):
        """The database filter is passed as a query parameter."""
        pool, _, cur = make_pool(rows=[])
        repo = SchemaRepository(pool)

        await repo.search_tables("%t%", database="mydb")

        call_args = cur.execute.call_args
        params = call_args[0][1]
        assert "mydb" in params

    async def test_aiomysql_error_raises_database_error(self):
        """Driver errors are wrapped in ``DatabaseError``."""
        pool, _, _ = make_pool(error=aiomysql.Error("fail"))
        repo = SchemaRepository(pool)

        with pytest.raises(DatabaseError, match="Failed to search tables"):
            await repo.search_tables("%x%")


# ---------------------------------------------------------------------------
# TableCache
# ---------------------------------------------------------------------------

class TestTableCache:
    """TTL-based per-database cache that serialises concurrent misses via a per-key lock."""
    async def test_cache_miss_queries_db_and_returns_set(self):
        """A cache miss queries the database and returns the table names as a set."""
        rows = [("users",), ("orders",)]
        pool, _, _ = make_pool(rows=rows)
        cache = TableCache(pool, ttl=300)

        result = await cache.get_valid_tables("mydb")

        assert result == {"users", "orders"}

    async def test_cache_hit_skips_db_query(self):
        """A second call within the TTL is served from the cache."""
        pool, _, cur = make_pool(rows=[("users",)])
        cache = TableCache(pool, ttl=300)

        await cache.get_valid_tables("mydb")   # populates cache
        await cache.get_valid_tables("mydb")   # should hit cache

        assert cur.execute.call_count == 1

    async def test_expired_cache_refreshes(self):
        """After the TTL expires the cache is refreshed from the database."""
        pool, _, cur = make_pool(rows=[("users",)])
        cache = TableCache(pool, ttl=300)

        await cache.get_valid_tables("mydb")
        cache._expires_at["mydb"] = 0.0       # force expiry
        await cache.get_valid_tables("mydb")

        assert cur.execute.call_count == 2

    async def test_thundering_herd_single_query(self):
        """Concurrent calls for the same database trigger a single query."""
        pool, _, cur = make_pool(rows=[("t",)])
        cache = TableCache(pool, ttl=300)

        await asyncio.gather(*[cache.get_valid_tables("mydb") for _ in range(10)])

        assert cur.execute.call_count == 1


# ---------------------------------------------------------------------------
# QueryRepository
# ---------------------------------------------------------------------------

class TestExecuteQuery:
    """``execute_query`` enforces row caps, detects truncation, and propagates timeouts."""
    async def test_returns_correct_structure(self):
        """The result has row_count, columns, rows, and limited=False."""
        rows = [{"id": 1, "name": "Alice"}]
        description = [("id", None, None, None, None, None, None),
                       ("name", None, None, None, None, None, None)]
        pool, _, cur = make_pool(rows=rows, description=description)
        cur.fetchall = AsyncMock(return_value=rows)
        repo = QueryRepository(pool, max_rows=500, query_timeout=30)

        result = await repo.execute_query("SELECT id, name FROM t")

        assert result["row_count"] == 1
        assert result["columns"] == ["id", "name"]
        assert result["rows"] == [{"id": 1, "name": "Alice"}]
        assert result["limited"] is False

    async def test_limited_true_when_extra_row_returned(self):
        # The repo fetches limit+1 rows to detect truncation without a second COUNT query.
        """An extra row beyond the limit sets ``limited`` and trims the result."""
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        description = [("id", None, None, None, None, None, None)]
        pool, _, cur = make_pool(rows=rows, description=description)
        cur.fetchall = AsyncMock(return_value=rows)
        repo = QueryRepository(pool, max_rows=500, query_timeout=30)

        result = await repo.execute_query("SELECT id FROM t", limit=2)

        assert result["limited"] is True
        assert result["row_count"] == 2
        assert len(result["rows"]) == 2

    async def test_limited_false_when_fewer_rows_than_limit(self):
        """``limited`` stays False when fewer rows than the limit are returned."""
        rows = [{"id": 1}, {"id": 2}]
        description = [("id", None, None, None, None, None, None)]
        pool, _, cur = make_pool(rows=rows, description=description)
        cur.fetchall = AsyncMock(return_value=rows)
        repo = QueryRepository(pool, max_rows=500, query_timeout=30)

        result = await repo.execute_query("SELECT id FROM t", limit=10)

        assert result["limited"] is False

    async def test_database_calls_select_db(self):
        """Passing a database selects it on the connection."""
        rows = [{"id": 1}]
        description = [("id", None, None, None, None, None, None)]
        pool, conn, cur = make_pool(rows=rows, description=description)
        cur.fetchall = AsyncMock(return_value=rows)
        repo = QueryRepository(pool, max_rows=500, query_timeout=30)

        await repo.execute_query("SELECT id FROM t", database="mydb")

        conn.select_db.assert_called_once_with("mydb")

    async def test_max_rows_caps_limit(self):
        """The requested limit is capped by ``max_rows``."""
        pool, _, cur = make_pool(rows=[], description=[])
        cur.fetchall = AsyncMock(return_value=[])
        repo = QueryRepository(pool, max_rows=10, query_timeout=30)

        result = await repo.execute_query("SELECT * FROM t", limit=999)

        assert result["row_count"] == 0

    async def test_timeout_raises_query_timeout_error(self):
        """A timeout is raised as ``QueryTimeoutError``."""
        from unittest.mock import patch
        from src.db.exceptions import QueryTimeoutError

        pool, _, _ = make_pool(rows=[])
        repo = QueryRepository(pool, max_rows=500, query_timeout=5)

        async def fake_wait_for(coro, **_):
            """Simulate ``asyncio.wait_for`` timing out."""
            coro.close()
            raise asyncio.TimeoutError

        with patch("src.db.repository.asyncio.wait_for", side_effect=fake_wait_for):
            with pytest.raises(QueryTimeoutError, match="exceeded the time limit"):
                await repo.execute_query("SELECT 1")

    async def test_timeout_is_subclass_of_timeout_error(self):
        # Callers can catch the built-in TimeoutError without importing our custom exception.
        """``QueryTimeoutError`` is catchable as the built-in ``TimeoutError``."""
        from unittest.mock import patch

        pool, _, _ = make_pool(rows=[])
        repo = QueryRepository(pool, max_rows=500, query_timeout=5)

        async def fake_wait_for(coro, **_):
            """Simulate ``asyncio.wait_for`` timing out."""
            coro.close()
            raise asyncio.TimeoutError

        with patch("src.db.repository.asyncio.wait_for", side_effect=fake_wait_for):
            with pytest.raises(TimeoutError):
                await repo.execute_query("SELECT 1")


class TestGetTableSample:
    """``get_table_sample`` validates the table name against the cache before querying."""
    async def test_valid_table_returns_sample(self):
        """A valid table returns its columns and sample rows."""
        rows = [{"id": 1, "name": "Alice"}]
        description = [("id", None, None, None, None, None, None),
                       ("name", None, None, None, None, None, None)]
        pool, _, cur = make_pool(rows=rows, description=description)
        cur.fetchall = AsyncMock(return_value=rows)

        repo = QueryRepository(pool, max_rows=500, query_timeout=30)
        repo._table_cache = MagicMock()
        repo._table_cache.get_valid_tables = AsyncMock(return_value={"users", "orders"})

        result = await repo.get_table_sample("mydb", "users", rows=5)

        assert result["database"] == "mydb"
        assert result["table"] == "users"
        assert result["columns"] == ["id", "name"]
        assert result["sample_rows"] == [{"id": 1, "name": "Alice"}]

    async def test_table_not_found_raises_value_error(self):
        """An unknown table raises ``ValueError``."""
        pool, _, _ = make_pool(rows=[])
        repo = QueryRepository(pool, max_rows=500, query_timeout=30)
        repo._table_cache = MagicMock()
        repo._table_cache.get_valid_tables = AsyncMock(return_value={"orders"})

        with pytest.raises(ValueError, match="not found"):
            await repo.get_table_sample("mydb", "ghost")

    async def test_aiomysql_error_raises_database_error(self):
        """Driver errors are wrapped in ``DatabaseError``."""
        pool, _, _ = make_pool(error=aiomysql.Error("fail"))
        repo = QueryRepository(pool, max_rows=500, query_timeout=30)
        repo._table_cache = MagicMock()
        repo._table_cache.get_valid_tables = AsyncMock(return_value={"users"})

        with pytest.raises(DatabaseError, match="Failed to sample"):
            await repo.get_table_sample("mydb", "users")

    async def test_rows_capped_at_20(self):
        """The sample size is capped at 20 rows."""
        rows = [{"id": i} for i in range(20)]
        description = [("id", None, None, None, None, None, None)]
        pool, _, cur = make_pool(rows=rows, description=description)
        cur.fetchall = AsyncMock(return_value=rows)

        repo = QueryRepository(pool, max_rows=500, query_timeout=30)
        repo._table_cache = MagicMock()
        repo._table_cache.get_valid_tables = AsyncMock(return_value={"users"})

        await repo.get_table_sample("mydb", "users", rows=50)

        sql_called = cur.execute.call_args[0][0]
        assert "LIMIT 20" in sql_called
