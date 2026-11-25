# tests/integration/conftest.py
"""
Session fixtures for integration tests against the real MySQL cluster.
Loads credentials from .env. Auto-skips all tests if the host is not reachable.
"""
from pathlib import Path

import asyncio

import pytest
import pytest_asyncio
import aiomysql
from dotenv import load_dotenv

from src.config import DatabaseConfig
from src.db.repository import SchemaRepository, QueryRepository
from src.db.secure_repository import SecureQueryRepository

load_dotenv(Path(__file__).parents[2] / ".env")


@pytest_asyncio.fixture(scope="session")
async def db_config() -> DatabaseConfig:
    """Load database configuration from the environment (requires a real .env file)."""
    return DatabaseConfig.from_env()


@pytest_asyncio.fixture(scope="session")
async def pool(db_config: DatabaseConfig):
    """Creates real pool. Skips entire session if connection fails."""
    try:
        p = await aiomysql.create_pool(  # type: ignore[misc]
            host=db_config.host,
            port=db_config.port,
            user=db_config.user,
            db=None,
            charset="utf8mb4",
            autocommit=True,
            minsize=db_config.pool_minsize,
            maxsize=db_config.pool_maxsize,
            connect_timeout=db_config.connect_timeout,
            init_command="SET SESSION TRANSACTION READ ONLY",
        )
    except (OSError, asyncio.TimeoutError, aiomysql.OperationalError) as exc:
        if isinstance(exc, aiomysql.OperationalError):
            err_code = exc.args[0] if exc.args else None
            if err_code not in {2003, 2005, 2013}:
                raise
        pytest.skip(f"MySQL host not reachable — integration tests skipped: {exc}")
    yield p
    p.close()
    await p.wait_closed()


@pytest_asyncio.fixture(scope="session")
async def schema_repo(pool) -> SchemaRepository:
    return SchemaRepository(pool)


@pytest_asyncio.fixture(scope="session")
async def query_repo(pool, db_config: DatabaseConfig) -> SecureQueryRepository:
    inner = QueryRepository(pool, max_rows=db_config.max_rows, query_timeout=db_config.query_timeout)
    return SecureQueryRepository(inner)


@pytest_asyncio.fixture(scope="session")
async def first_database(schema_repo: SchemaRepository) -> str:
    """Returns the first available database in the cluster."""
    dbs = await schema_repo.list_databases()
    assert dbs, "No databases found in cluster"
    return dbs[0]


@pytest_asyncio.fixture(scope="session")
async def first_table(schema_repo: SchemaRepository, first_database: str) -> str:
    """Returns the name of the first table in the first database."""
    tables = await schema_repo.list_tables(first_database)
    assert tables, f"No tables found in '{first_database}'"
    return tables[0]["table_name"]
