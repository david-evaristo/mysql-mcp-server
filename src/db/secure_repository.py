"""
Security decorator over QueryRepository (OCP / DIP).

SecureQueryRepository intercepts all operations and applies validations
before delegating to the real repository. QueryRepository does not need
to know validations exist — it can be tested in full isolation.
"""
import re
from typing import Any

from .repository import QueryRepository
from .query_guard import validate_query, QueryValidator, build_default_validators

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")


class SecureQueryRepository:
    """
    Wrapper that adds security to QueryRepository.

    Implements the same public interface — can replace QueryRepository
    anywhere without the caller noticing (LSP).
    """

    def __init__(
        self,
        inner: QueryRepository,
        validators: list[QueryValidator] | None = None,
    ) -> None:
        self._inner = inner
        self._validators = validators or build_default_validators()

    @staticmethod
    def _validate_identifier(name: str) -> None:
        if not _IDENTIFIER_RE.match(name):
            raise ValueError(
                "Invalid identifier — must contain only letters, digits, underscores, or $."
            )

    async def execute_query(
        self,
        sql: str,
        database: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        validate_query(sql, self._validators)
        if database is not None:
            self._validate_identifier(database)
        return await self._inner.execute_query(sql, database, limit)

    async def get_table_sample(
        self, database: str, table: str, rows: int = 5
    ) -> dict[str, Any]:
        self._validate_identifier(database)
        self._validate_identifier(table)
        return await self._inner.get_table_sample(database, table, rows)
