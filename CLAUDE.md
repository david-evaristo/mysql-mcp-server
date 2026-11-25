# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # fill in real credentials

# Run (stdio — Claude Desktop / Cursor)
python main.py

# Run (HTTP)
MCP_TRANSPORT=http python -m src.server

# Inspect available tools interactively
fastmcp dev src/server.py

# Tests (unit only — no DB required)
pytest tests/ --ignore=tests/integration

# Tests (all, including integration — requires real MySQL)
pytest

# Single test file
pytest tests/test_query_guard.py

# With coverage
pytest --cov=src --ignore=tests/integration
```

## Architecture

### Entry points

| File | Purpose |
|---|---|
| `main.py` | stdio transport — Claude Desktop, Cursor |
| `app.py` | ASGI/HTTP — Hugging Face Space |
| `src/server.py` | Selects transport via `MCP_TRANSPORT` env (`stdio` or `http`) |

All three import `mcp` from `src/initialization.py`, which is the FastMCP singleton.

### Layer overview

```
FastMCP tools/resources (src/tools/mysql.py, src/resources/mysql.py)
    └─ run_tool (src/handler.py)  ← unified error handling
        └─ SecureQueryRepository (src/db/secure_repository.py)  ← SQL validation decorator
            └─ QueryRepository / SchemaRepository (src/db/repository.py)  ← aiomysql queries
                └─ ConnectionPool (src/db/lifespan.py)  ← lazy pool, double-checked locking
```

- **`src/initialization.py`** — creates the FastMCP singleton at import time, wires `DatabaseConfig`, lifespan, tools, and resources.
- **`src/db/lifespan.py`** — `ConnectionPool` (lazy `aiomysql` pool), `AppContext` (repository factory), `IAppContext` Protocol (for mocking in tests).
- **`src/db/repository.py`** — `SchemaRepository` (metadata: databases/tables/columns/indexes), `QueryRepository` (query execution + `get_table_sample`), `TableCache` (TTL-based per-DB table name cache, 5 min, max 50 DBs).
- **`src/db/secure_repository.py`** — `SecureQueryRepository` wraps `QueryRepository`. Runs `validate_query` before delegating and validates database/table identifiers against `^[A-Za-z0-9_$]+$`.
- **`src/db/query_guard.py`** — Two validators: `WriteKeywordValidator` (blocks write SQL keywords even inside comments) and `SelectOnlyValidator` (requires `SELECT` prefix). `add_limit()` injects or caps `LIMIT` at the root query level, preserving subquery limits.
- **`src/config.py`** — `DatabaseConfig` frozen dataclass, read once from env vars. Required: `MYSQL_HOST`, `MYSQL_USER`.
- **`src/handler.py`** — `run_tool()`: `ValueError` → re-raise as-is; `DatabaseError` → raise `RuntimeError` with generic message.

### MCP tools vs resources

Tools (`src/tools/mysql.py`): `list_databases`, `list_tables`, `describe_table`, `execute_query`, `search_tables`, `get_table_sample`.

Resources (`src/resources/mysql.py`): `schema://databases`, `schema://{database}/tables` — same data as tools but as plain-text MCP resources.

### Testing

- Unit tests (`tests/`) use `make_pool()` / `make_conn()` from `conftest.py` to mock the aiomysql driver without a real connection.
- Integration tests (`tests/integration/`) hit the real cluster. They auto-skip with `pytest.skip()` if the host is unreachable. Run selectively with `-m integration`.

### Key env vars

| Variable | Default | Purpose |
|---|---|---|
| `MYSQL_CONNECTION_MODE` | `teleport` | `teleport` (tunnel local) or `direct` (MySQL direto) |
| `MYSQL_HOST` | — | Host do banco ou proxy local — `127.0.0.1` em teleport (required) |
| `MYSQL_PORT` | `54855` (teleport) / `3306` (direct) | Porta MySQL |
| `MYSQL_USER` | — | Required |
| `MYSQL_PASSWORD` | — | Required when `MYSQL_CONNECTION_MODE=direct` |
| `MYSQL_DATABASE` | — | Optional default database |
| `MYSQL_SSL_CA` | — | Optional CA file path for TLS in direct mode |
| `MCP_MAX_ROWS` | `500` | Hard cap on rows returned |
| `MCP_TRANSPORT` | `http` | `stdio` or `http` |
| `MCP_QUERY_TIMEOUT` | `30` | Seconds before query is cancelled |
| `MCP_CONNECT_TIMEOUT` | `10` | Seconds before connection attempt is aborted |
| `MCP_RATE_LIMIT` | `60` | Max tool calls per minute; `0` = disabled |
| `MCP_POOL_MIN` / `MCP_POOL_MAX` | `2` / `10` | aiomysql pool size |
| `PORT` | `8000` | HTTP listen port |
