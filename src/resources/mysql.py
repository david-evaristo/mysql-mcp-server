"""
MCP resources — explicitly registered via register_resources(mcp).

Resources delegate to SchemaRepository — no coupling to the driver.
"""
import re
from fastmcp import Context, FastMCP

from src.handler import run_tool
from src.db import get_schema_repo
from src.logging_config import logger


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")


def register_resources(mcp: FastMCP) -> None:
    """Registers all resources on the provided MCP server."""

    @mcp.resource("schema://databases")
    async def resource_databases(ctx: Context) -> str:
        """Lists all cluster databases as plain text."""
        repo = await get_schema_repo(ctx)
        dbs = await run_tool("resource_databases", repo.list_databases(), logger)
        return "Databases available in the MySQL cluster:\n" + "\n".join(f"  - {d}" for d in dbs)

    @mcp.resource("schema://{database}/tables")
    async def resource_tables(database: str, ctx: Context) -> str:
        """Lists the tables in a specific database."""
        if not _IDENTIFIER_RE.match(database):
            raise ValueError(
                "Invalid database name — must contain only letters, digits, underscores, or $."
            )

        repo = await get_schema_repo(ctx)
        tables = await run_tool("resource_tables", repo.list_tables(database), logger)
        lines = [f"Tables in '{database}':\n"]
        for t in tables:
            table_name = t.get("table_name") or "<unknown>"
            size = t.get("size_mb") or 0
            approx = t.get("approx_rows") if t.get("approx_rows") is not None else "?"
            lines.append(f"  - {table_name}  (~{approx} rows, {size} MB)")
        return "\n".join(lines)
