# tests/integration/test_schema.py
"""
Integration tests for SchemaRepository.
Require a real connection to the MySQL cluster.
"""
import pytest

from src.db.repository import SchemaRepository


pytestmark = pytest.mark.integration


class TestListDatabasesIntegration:
    async def test_returns_non_empty_list(self, schema_repo: SchemaRepository):
        result = await schema_repo.list_databases()

        assert isinstance(result, list)
        assert len(result) > 0

    async def test_result_is_sorted(self, schema_repo: SchemaRepository):
        result = await schema_repo.list_databases()

        assert result == sorted(result)

    async def test_system_databases_excluded(self, schema_repo: SchemaRepository):
        result = await schema_repo.list_databases()

        for system_db in ("information_schema", "performance_schema", "mysql", "sys"):
            assert system_db not in result


class TestListTablesIntegration:
    async def test_returns_tables_for_existing_database(
        self, schema_repo: SchemaRepository, first_database: str
    ):
        result = await schema_repo.list_tables(first_database)

        assert isinstance(result, list)
        assert len(result) > 0

    async def test_each_table_has_expected_keys(
        self, schema_repo: SchemaRepository, first_database: str
    ):
        result = await schema_repo.list_tables(first_database)

        for row in result:
            assert "table_name" in row
            assert "table_type" in row

    async def test_nonexistent_database_raises(self, schema_repo: SchemaRepository):
        with pytest.raises(ValueError, match=r"not found|has no tables"):
            await schema_repo.list_tables("__nonexistent_db_xyzzy__")


class TestDescribeTableIntegration:
    async def test_returns_columns_and_indexes(
        self,
        schema_repo: SchemaRepository,
        first_database: str,
        first_table: str,
    ):
        result = await schema_repo.describe_table(first_database, first_table)

        assert result["database"] == first_database
        assert result["table"] == first_table
        assert isinstance(result["columns"], list)
        assert isinstance(result["indexes"], list)
        assert len(result["columns"]) > 0

    async def test_each_column_has_expected_keys(
        self,
        schema_repo: SchemaRepository,
        first_database: str,
        first_table: str,
    ):
        result = await schema_repo.describe_table(first_database, first_table)

        # information_schema.COLUMNS returns uppercase keys (no aliases in describe_table query)
        for col in result["columns"]:
            assert "COLUMN_NAME" in col
            assert "COLUMN_TYPE" in col
            assert "IS_NULLABLE" in col

    async def test_nonexistent_table_raises(
        self, schema_repo: SchemaRepository, first_database: str
    ):
        with pytest.raises(ValueError, match="not found"):
            await schema_repo.describe_table(first_database, "__ghost_table_xyzzy__")


class TestSearchTablesIntegration:
    async def test_wildcard_returns_results(self, schema_repo: SchemaRepository):
        result = await schema_repo.search_tables("%")

        assert isinstance(result, list)
        assert len(result) > 0

    async def test_each_result_has_database_and_table_keys(
        self, schema_repo: SchemaRepository
    ):
        result = await schema_repo.search_tables("%")

        for row in result:
            assert "database" in row
            assert "table" in row

    async def test_specific_pattern_filters_results(
        self, schema_repo: SchemaRepository, first_database: str, first_table: str
    ):
        # Use first 3 characters of table name as prefix pattern
        assert len(first_table) >= 3, f"Table name '{first_table}' is too short for prefix test"
        prefix = first_table[:3]
        escaped_prefix = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        result = await schema_repo.search_tables(f"{escaped_prefix}%", database=first_database)

        assert isinstance(result, list)
        assert result, f"No matches returned for prefix {prefix!r} in {first_database!r}"
        assert any(row["table"] == first_table for row in result)
        for row in result:
            assert row["table"].startswith(prefix)

    async def test_impossible_pattern_returns_empty(
        self, schema_repo: SchemaRepository
    ):
        result = await schema_repo.search_tables("xyzzyNoMatchEver12345Literal")

        assert result == []
