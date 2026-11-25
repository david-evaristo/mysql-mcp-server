from fastmcp import Context

from .lifespan import IAppContext
from .repository import SchemaRepository
from .secure_repository import SecureQueryRepository


def _get_app_context(ctx: Context) -> IAppContext:
    """Extracts and validates the MCP server lifespan context."""
    if ctx.request_context is None:
        raise RuntimeError("No request context available.")
    lifespan_ctx = ctx.request_context.lifespan_context
    if not isinstance(lifespan_ctx, IAppContext):
        raise TypeError(
            f"Lifespan context does not implement IAppContext: "
            f"{type(lifespan_ctx).__name__}. Check the lifespan configuration."
        )
    return lifespan_ctx


async def get_schema_repo(ctx: Context) -> SchemaRepository:
    return await _get_app_context(ctx).get_schema_repo()


async def get_query_repo(ctx: Context) -> SecureQueryRepository:
    return await _get_app_context(ctx).get_query_repo()
