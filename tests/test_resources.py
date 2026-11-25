# tests/test_resources.py
from unittest.mock import AsyncMock, MagicMock, patch


def _build_registered_handlers():
    """Register resources on a fake MCP and return {uri: handler}."""
    from src.resources.mysql import register_resources
    from fastmcp import FastMCP

    registered = {}
    mcp = MagicMock(spec=FastMCP)

    def fake_resource(uri):
        def decorator(fn):
            registered[uri] = fn
            return fn
        return decorator

    mcp.resource = fake_resource
    register_resources(mcp)
    return registered


_HANDLERS = _build_registered_handlers()


class TestResourceDatabases:
    async def test_lists_databases_as_plain_text(self):
        ctx = MagicMock()
        dbs = ["db1", "db2", "db3"]

        with patch("src.resources.mysql.get_schema_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.resources.mysql.run_tool", new=AsyncMock(return_value=dbs)):
            result = await _HANDLERS["schema://databases"](ctx)

        assert "Databases available" in result
        assert "db1" in result
        assert "db2" in result
        assert "db3" in result

    async def test_each_database_on_its_own_line(self):
        ctx = MagicMock()
        dbs = ["alpha", "beta"]

        with patch("src.resources.mysql.get_schema_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.resources.mysql.run_tool", new=AsyncMock(return_value=dbs)):
            result = await _HANDLERS["schema://databases"](ctx)

        lines = result.splitlines()
        assert any("alpha" in line for line in lines)
        assert any("beta" in line for line in lines)
        assert result.count("alpha") == 1
        assert result.count("beta") == 1


class TestResourceTables:
    async def test_lists_tables_with_metadata(self):
        ctx = MagicMock()
        tables = [
            {"table_name": "users", "approx_rows": 1000, "size_mb": 2.5},
            {"table_name": "orders", "approx_rows": None, "size_mb": None},
        ]

        with patch("src.resources.mysql.get_schema_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.resources.mysql.run_tool", new=AsyncMock(return_value=tables)):
            result = await _HANDLERS["schema://{database}/tables"](database="mydb", ctx=ctx)

        assert "mydb" in result
        assert "users" in result
        assert "orders" in result
        assert "1000" in result

    async def test_table_with_null_metadata_uses_defaults(self):
        ctx = MagicMock()
        tables = [{"table_name": "events", "approx_rows": None, "size_mb": None}]

        with patch("src.resources.mysql.get_schema_repo", new=AsyncMock(return_value=MagicMock())), \
             patch("src.resources.mysql.run_tool", new=AsyncMock(return_value=tables)):
            result = await _HANDLERS["schema://{database}/tables"](database="db", ctx=ctx)

        assert "events" in result
        assert "?" in result    # fallback para approx_rows None
        assert "0" in result    # fallback para size_mb None

    async def test_invalid_database_error_does_not_echo_value(self):
        ctx = MagicMock()

        import pytest
        with pytest.raises(ValueError) as exc_info:
            await _HANDLERS["schema://{database}/tables"](database="db;drop--tables", ctx=ctx)

        assert "db;drop--tables" not in str(exc_info.value)
