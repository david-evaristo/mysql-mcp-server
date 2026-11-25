# tests/integration/test_query.py
"""
Integration tests for QueryRepository (via SecureQueryRepository).
Require a real connection to the MySQL cluster.
"""
import pytest

from src.db.secure_repository import SecureQueryRepository


pytestmark = pytest.mark.integration


class TestExecuteQueryIntegration:
    async def test_simple_select_returns_structure(
        self, query_repo: SecureQueryRepository
    ):
        result = await query_repo.execute_query("SELECT 1 AS n")

        assert "rows" in result
        assert "columns" in result
        assert "row_count" in result
        assert "limited" in result
        assert result["row_count"] == 1
        assert result["columns"] == ["n"]
        assert result["rows"][0]["n"] == 1

    async def test_limit_respected(
        self,
        query_repo: SecureQueryRepository,
        first_database: str,
        first_table: str,
    ):
        result = await query_repo.execute_query(
            f"SELECT * FROM `{first_database}`.`{first_table}`",
            limit=3,
        )

        assert result["row_count"] <= 3
        assert len(result["rows"]) <= 3

    async def test_limited_flag_true_when_more_data_exists(
        self, query_repo: SecureQueryRepository
    ):
        # Use a synthetic 3-row dataset so limited is guaranteed True at limit=1
        result = await query_repo.execute_query(
            "SELECT 1 AS n UNION SELECT 2 UNION SELECT 3",
            limit=1,
        )

        assert result["limited"] is True
        assert result["row_count"] == 1

    async def test_limited_flag_false_for_small_result(
        self, query_repo: SecureQueryRepository
    ):
        result = await query_repo.execute_query(
            "SELECT 1 AS n UNION SELECT 2", limit=100
        )

        assert result["limited"] is False
        assert result["row_count"] == 2

    async def test_database_qualifier_works(
        self,
        query_repo: SecureQueryRepository,
        first_database: str,
        first_table: str,
    ):
        result = await query_repo.execute_query(
            f"SELECT * FROM `{first_table}`",
            database=first_database,
            limit=1,
        )

        assert "rows" in result

    async def test_columns_match_table_schema(
        self,
        query_repo: SecureQueryRepository,
        schema_repo,
        first_database: str,
        first_table: str,
    ):
        described = await schema_repo.describe_table(first_database, first_table)
        expected_cols = {c["COLUMN_NAME"] for c in described["columns"]}

        result = await query_repo.execute_query(
            f"SELECT * FROM `{first_database}`.`{first_table}`",
            limit=1,
        )

        # SELECT * may exclude INVISIBLE or generated columns present in information_schema
        assert set(result["columns"]).issubset(expected_cols)


class TestGetTableSampleIntegration:
    async def test_returns_sample_structure(
        self,
        query_repo: SecureQueryRepository,
        first_database: str,
        first_table: str,
    ):
        result = await query_repo.get_table_sample(first_database, first_table, rows=3)

        assert result["database"] == first_database
        assert result["table"] == first_table
        assert "columns" in result
        assert "sample_rows" in result
        assert len(result["sample_rows"]) <= 3

    async def test_nonexistent_table_raises(
        self,
        query_repo: SecureQueryRepository,
        first_database: str,
    ):
        with pytest.raises(ValueError, match=r"__ghost_table_xyzzy__.*not found"):
            await query_repo.get_table_sample(
                first_database, "__ghost_table_xyzzy__", rows=1
            )
