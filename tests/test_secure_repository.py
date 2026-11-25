import pytest
from unittest.mock import AsyncMock, MagicMock

from src.db.secure_repository import SecureQueryRepository
from src.db.repository import QueryRepository


def _make_inner():
    inner = MagicMock(spec=QueryRepository)
    inner.execute_query = AsyncMock(
        return_value={"rows": [], "row_count": 0, "columns": [], "limited": False}
    )
    inner.get_table_sample = AsyncMock(
        return_value={"database": "db", "table": "t", "columns": [], "sample_rows": []}
    )
    return inner


class TestSecureExecuteQuery:
    async def test_valid_select_delegates_to_inner(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        await repo.execute_query("SELECT 1")

        inner.execute_query.assert_called_once_with("SELECT 1", None, 100)

    async def test_write_keyword_raises_before_calling_inner(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        with pytest.raises(ValueError, match="write operation"):
            await repo.execute_query("DROP TABLE t")

        inner.execute_query.assert_not_called()

    async def test_non_select_raises_before_calling_inner(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        with pytest.raises(ValueError, match="write operation"):
            await repo.execute_query("INSERT INTO t VALUES (1)")

        inner.execute_query.assert_not_called()

    async def test_invalid_database_identifier_raises(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        with pytest.raises(ValueError, match="Invalid identifier"):
            await repo.execute_query("SELECT 1", database="db;drop")

        inner.execute_query.assert_not_called()

    async def test_valid_identifier_with_dollar_sign_passes(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        await repo.execute_query("SELECT 1", database="db$name")

        inner.execute_query.assert_called_once()

    async def test_none_database_skips_identifier_check(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        await repo.execute_query("SELECT 1", database=None)

        inner.execute_query.assert_called_once()

    async def test_limit_is_forwarded(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        await repo.execute_query("SELECT 1", limit=50)

        inner.execute_query.assert_called_once_with("SELECT 1", None, 50)


class TestSecureGetTableSample:
    async def test_valid_args_delegates_to_inner(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        await repo.get_table_sample("mydb", "users")

        inner.get_table_sample.assert_called_once_with("mydb", "users", 5)

    async def test_invalid_database_raises_before_inner(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        with pytest.raises(ValueError, match="Invalid identifier"):
            await repo.get_table_sample("db;x", "t")

        inner.get_table_sample.assert_not_called()

    async def test_invalid_table_raises_before_inner(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        with pytest.raises(ValueError, match="Invalid identifier"):
            await repo.get_table_sample("db", "t;drop")

        inner.get_table_sample.assert_not_called()

    async def test_rows_param_forwarded(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        await repo.get_table_sample("db", "t", rows=10)

        inner.get_table_sample.assert_called_once_with("db", "t", 10)


class TestIdentifierErrorLeakPrevention:
    async def test_invalid_database_error_does_not_echo_value(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        with pytest.raises(ValueError) as exc_info:
            await repo.execute_query("SELECT 1", database="db;drop--tables")

        assert "db;drop--tables" not in str(exc_info.value)

    async def test_invalid_table_error_does_not_echo_value(self):
        inner = _make_inner()
        repo = SecureQueryRepository(inner)

        with pytest.raises(ValueError) as exc_info:
            await repo.get_table_sample("db", "t' OR '1'='1")

        assert "t' OR '1'='1" not in str(exc_info.value)
