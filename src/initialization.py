"""
Singleton for the FastMCP instance.

`mcp` is created at import time (required for the lifespan), but `from_env()`
and tool/resource registration are isolated in `_create_mcp()` to simplify
mocking in tests.
"""
from functools import partial

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import DatabaseConfig
from src.db.lifespan import build_lifespan
from src.tools.mysql import register_tools
from src.resources.mysql import register_resources
from src.rate_limiter import RateLimiter
from src import handler as _handler

load_dotenv()


def _create_mcp() -> FastMCP:
    """
    Instantiate and fully configure the FastMCP server.

    Separated from module-level code so tests can patch ``DatabaseConfig.from_env``
    before the singleton is created, without having to reload the module.
    """
    config = DatabaseConfig.from_env()
    if config.rate_limit > 0:
        _handler.configure_rate_limiter(RateLimiter(limit=config.rate_limit))
    else:
        _handler.configure_rate_limiter(None)
    server = FastMCP(
        name="mysql-mcp-server",
        instructions=(
            "Read-only query server for a MySQL cluster, accessed via "
            "a Teleport proxy running on localhost. "
            "Use list_databases to see available databases, list_tables to explore "
            "the schema, describe_table to see columns, and execute_query to query data. "
            "If the connection fails, ask the user to verify that a Teleport Database "
            "Access tunnel ('tsh db login' + 'tsh proxy db --tunnel') is running."
        ),
        lifespan=partial(build_lifespan, config=config),
    )
    register_tools(server)
    register_resources(server)

    @server.custom_route("/health", methods=["GET"])
    async def _health(request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    return server


mcp = _create_mcp()
