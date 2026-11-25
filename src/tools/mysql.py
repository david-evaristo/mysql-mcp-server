"""
MCP tools — explicitly registered via register_tools(mcp).

Tools delegate all logic to repositories — they do not know about aiomysql.
"""
from typing import Any

from fastmcp import Context, FastMCP

from src import audit
from src.db import get_query_repo, get_schema_repo
from src.handler import run_tool
from src.logging_config import logger


def register_tools(mcp: FastMCP) -> None:
    """Registers all tools on the provided MCP server."""

    @mcp.tool
    async def list_databases(ctx: Context) -> list[str]:
        """
        Lists all databases available in the MySQL cluster.
        Use this tool first to discover which databases exist.
        """
        repo = await get_schema_repo(ctx)
        return await run_tool("list_databases", repo.list_databases(), logger)

    @mcp.tool
    async def list_tables(database: str, ctx: Context) -> list[dict]:
        """
        Lists all tables in a specific database with basic information.

        Args:
            database: Database name (e.g. my_database)
            ctx: Context
        """
        repo = await get_schema_repo(ctx)
        return await run_tool("list_tables", repo.list_tables(database), logger)

    @mcp.tool
    async def describe_table(database: str, table: str, ctx: Context) -> dict:
        """
        Returns the full structure of a table: columns, types, indexes, and constraints.

        Args:
            database: Database name
            table:    Table name
            ctx: Context
        """
        repo = await get_schema_repo(ctx)
        return await run_tool("describe_table", repo.describe_table(database, table), logger)

    @mcp.tool
    async def execute_query(
        sql: str,
        ctx: Context,
        database: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Executes a SELECT query on the MySQL cluster. Read-only access only.

        Args:
            sql:      SQL query — SELECT only. Use `database.table` or set `database`.
            ctx: Context
            database: (optional) Default database for the query. Can be omitted when using
                      full qualification (e.g. my_database.users).
            limit:    Maximum rows returned (default 100, maximum 500).
        """
        repo = await get_query_repo(ctx)
        status = "error"
        try:
            result = await run_tool("execute_query", repo.execute_query(sql, database, limit), logger)
            status = "success"
            return result
        finally:
            audit.log_query_event(tool="execute_query", sql=sql, database=database, status=status)

    @mcp.tool
    async def search_tables(
        pattern: str,
        ctx: Context,
        database: str | None = None,
    ) -> list[dict]:
        """
        Searches tables by name (supports SQL LIKE pattern: % and _).

        Args:
            pattern:  Search pattern (e.g. '%user%', '%payment%', 'account_%')
            ctx: Context
            database: (optional) Restricts the search to a specific database.
        """
        repo = await get_schema_repo(ctx)
        return await run_tool("search_tables", repo.search_tables(pattern, database), logger)

    @mcp.tool
    async def get_table_sample(
        database: str,
        table: str,
        ctx: Context,
        rows: int = 5,
    ) -> dict[str, Any]:
        """
        Returns a sample of rows from a table to understand the data format.

        Args:
            database: Database name
            table:    Table name
            ctx: Context
            rows:     Number of sample rows (default 5, maximum 20)
        """
        repo = await get_query_repo(ctx)
        sql_repr = f"SELECT * FROM `{database}`.`{table}` LIMIT {min(rows, 20)}"
        status = "error"
        try:
            result = await run_tool("get_table_sample", repo.get_table_sample(database, table, rows), logger)
            status = "success"
            return result
        finally:
            audit.log_query_event(tool="get_table_sample", sql=sql_repr, database=database, status=status)
