"""
Verifies that audit.log_query_event fires from the actual execute_query and
get_table_sample tool closures in src/tools/mysql.py. Covers both success
(status="success") and exception paths (status="error") — audit always fires
via try/finally regardless of run_tool outcome.

Uses a MockMCP to capture the closures without spinning up a FastMCP server.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import src.audit as audit


def _build_tool_registry():
    """Register tools on a fake MCP and return {name: fn}."""
    from src.tools.mysql import register_tools

    registry = {}

    class MockMCP:
        def tool(self, fn):
            registry[fn.__name__] = fn
            return fn

    register_tools(MockMCP())
    return registry


@pytest.fixture
def tools():
    """Fixture providing registered tool closures."""
    return _build_tool_registry()


class TestExecuteQueryAudit:
    async def test_execute_query_calls_audit_on_success(self, tools):
        """Audit fires once with correct args when execute_query succeeds."""
        sql = "SELECT 1"
        database = "mydb"
        fake_result = {"rows": [], "row_count": 0, "columns": [], "limited": False}
        ctx = MagicMock()

        with patch("src.tools.mysql.get_query_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.tools.mysql.run_tool", new=AsyncMock(return_value=fake_result)), \
             patch.object(audit, "log_query_event") as mock_audit:
            result = await tools["execute_query"](sql=sql, ctx=ctx, database=database)

        assert result == fake_result
        mock_audit.assert_called_once_with(
            tool="execute_query", sql=sql, database=database, status="success"
        )

    async def test_execute_query_audit_fires_with_error_status_on_validation_error(self, tools):
        """Audit fires with status='error' when run_tool raises ValueError (blocked query)."""
        ctx = MagicMock()

        with patch("src.tools.mysql.get_query_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.tools.mysql.run_tool", new=AsyncMock(side_effect=ValueError("blocked"))), \
             patch.object(audit, "log_query_event") as mock_audit:
            with pytest.raises(ValueError, match="blocked"):
                await tools["execute_query"](sql="DROP TABLE x", ctx=ctx, database="mydb")

        mock_audit.assert_called_once_with(
            tool="execute_query", sql="DROP TABLE x", database="mydb", status="error"
        )


class TestGetTableSampleAudit:
    async def test_get_table_sample_calls_audit_on_success(self, tools):
        """Audit fires once with correct sql_repr when get_table_sample succeeds."""
        database = "mydb"
        table = "users"
        rows = 5
        fake_result = {"rows": [], "row_count": 0, "columns": [], "limited": False}
        ctx = MagicMock()

        with patch("src.tools.mysql.get_query_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.tools.mysql.run_tool", new=AsyncMock(return_value=fake_result)), \
             patch.object(audit, "log_query_event") as mock_audit:
            result = await tools["get_table_sample"](database=database, table=table, ctx=ctx, rows=rows)

        assert result == fake_result
        expected_sql = f"SELECT * FROM `{database}`.`{table}` LIMIT {rows}"
        mock_audit.assert_called_once_with(
            tool="get_table_sample", sql=expected_sql, database=database, status="success"
        )

    async def test_get_table_sample_audit_fires_with_error_status_on_error(self, tools):
        """Audit fires with status='error' when run_tool raises (any error)."""
        ctx = MagicMock()

        with patch("src.tools.mysql.get_query_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.tools.mysql.run_tool", new=AsyncMock(side_effect=RuntimeError("db down"))), \
             patch.object(audit, "log_query_event") as mock_audit:
            with pytest.raises(RuntimeError, match="db down"):
                await tools["get_table_sample"](database="mydb", table="users", ctx=MagicMock(), rows=5)

        mock_audit.assert_called_once_with(
            tool="get_table_sample",
            sql="SELECT * FROM `mydb`.`users` LIMIT 5",
            database="mydb",
            status="error",
        )
