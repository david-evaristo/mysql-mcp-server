# Code Review Guidelines

## Always check

- Every query must go through `SecureQueryRepository` (`src/db/secure_repository.py`), never `QueryRepository` directly
- New MCP tools must use `run_tool()` from `src/handler.py` for unified error handling
- Required environment variables (`MYSQL_HOST`, `MYSQL_USER`) must never have hardcoded default values
- No code should bypass `validate_query` from `src/db/query_guard.py`
- Database and table identifiers must be validated against `^[A-Za-z0-9_$]+$`
- New configuration parameters must be added to the `DatabaseConfig` dataclass in `src/config.py`
- The FastMCP singleton must be imported from `src/initialization.py`, never re-instantiated

## Style

- Schema-reading tools belong in `src/tools/mysql.py`
- MCP resources belong in `src/resources/mysql.py`
- Unit tests must not use a real database connection — use `make_pool()` / `make_conn()` from `conftest.py`
- Integration tests must use `pytest.mark.integration` and auto-skip if the host is unreachable

## Skip

- Files under `infrastructure/`
- `.example`, `.env*`, and `*.lock` files
- Auto-generated files
