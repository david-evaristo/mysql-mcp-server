"""
Query security validation — OCP / SRP.

Each rule is a separate class that implements QueryValidator.
To add new rules, simply create a new class and register it in
build_default_validators(), without modifying existing ones.
"""
import hashlib
import logging
import re
from typing import Protocol

import sqlparse

_audit_logger = logging.getLogger("mysql-mcp.audit")

# Single constant — shared by query_guard and repository (OCP / DRY)
WRITE_KEYWORDS: frozenset[str] = frozenset({
    "insert", "update", "delete", "drop", "truncate",
    "alter", "create", "replace", "call", "exec",
    "grant", "revoke", "lock", "unlock",
    # File I/O — embeds writes inside SELECT
    "outfile", "dumpfile", "load",
    # SELECT INTO <table> | SELECT INTO @var — creates table (PostgreSQL) or assigns variable (MySQL)
    "into",
    # Prepared statement bypass (exec already blocked, execute is a different token)
    "execute", "prepare", "deallocate",
    # DDL / admin
    "set", "rename", "flush",
    # Server operations
    "kill", "shutdown", "handler",
})

SYSTEM_DATABASES: frozenset[str] = frozenset({
    "information_schema", "performance_schema", "mysql", "sys"
})


class QueryValidator(Protocol):
    """Validation interface — ISP: each validator has a single responsibility."""

    def validate(self, sql: str) -> None: ...


class WriteKeywordValidator:
    """Blocks write keywords."""

    def __init__(self, blocked: frozenset[str] = WRITE_KEYWORDS) -> None:
        self._blocked = blocked

    def validate(self, sql: str) -> None:
        # Check raw SQL (including comment content) so write keywords cannot be hidden in comments.
        lowered = sql.lower()
        found = {kw for kw in self._blocked if re.search(rf"\b{kw}\b", lowered)}
        if found:
            raise ValueError(
                f"Query blocked — write operation(s) detected: {found}. "
                "This server is read-only."
            )


_COMMENT_RE = re.compile(r"(--[^\n]*|#[^\n]*|/\*.*?\*/)", re.DOTALL)
_LIMIT_RE = re.compile(r"\bLIMIT\s+\d+\b", re.IGNORECASE)


def _remove_comments(sql: str) -> str:
    """Remove SQL comments — used only by add_limit().

    SqlParseValidator delegates comment handling to sqlparse itself.
    The two paths use different parsers (_COMMENT_RE vs. sqlparse tokenizer)
    and may diverge in extreme edge cases.
    """
    return _COMMENT_RE.sub(" ", sql)


class SqlParseValidator:
    """Ensures only SELECT queries are executed and blocks multiple statements."""

    @staticmethod
    def validate(sql: str) -> None:
        parsed = sqlparse.parse(sql)
        # Reject any query containing unparseable (UNKNOWN) statements for security
        unknown_statements = [stmt for stmt in parsed if stmt.tokens and stmt.get_type() == "UNKNOWN"]
        if unknown_statements:
            raise ValueError("Query contains unparseable SQL syntax.")
            
        statements = [stmt for stmt in parsed if stmt.tokens]
        
        if not statements:
            raise ValueError("No valid SQL statement found.")
            
        if len(statements) > 1:
            raise ValueError("Multiple statements are not allowed.")
            
        stmt = statements[0]

        if stmt.get_type() != "SELECT":
            raise ValueError("Only SELECT queries are allowed.")


_DEFAULT_VALIDATORS: tuple[QueryValidator, ...] = (
    WriteKeywordValidator(),
    SqlParseValidator(),
)


def build_default_validators() -> list[QueryValidator]:
    return list(_DEFAULT_VALIDATORS)


def validate_query(sql: str, validators: list[QueryValidator] | None = None) -> None:
    """Runs all registered validators."""
    for v in (validators if validators is not None else _DEFAULT_VALIDATORS):
        try:
            v.validate(sql)
        except ValueError as exc:
            _audit_logger.warning(
                "Query blocked [%s]: %s | sql_sha256=%s",
                type(v).__name__,
                exc,
                hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
            raise


def add_limit(sql: str, limit: int) -> str:
    """Ensures the LIMIT never exceeds the configured maximum.

    Applies the cap only to the root-level LIMIT, preserving LIMITs in subqueries.
    Strips comments before parsing to prevent matches inside comment text.
    Handles both LIMIT n and LIMIT offset, n (MySQL offset syntax).
    """
    # Strip comments first to prevent matching LIMIT keywords inside comment text
    clean = _remove_comments(sql).rstrip().rstrip(";")
    depth = 0
    last_limit_pos = -1
    last_limit_end = -1
    existing_limit: int | None = None
    existing_offset: int | None = None

    # Identify quoted spans to ignore them during parsing
    quotes: list[tuple[int, int]] = []
    in_quote: str | None = None
    escaped = False
    q_start = -1
    for i, char in enumerate(clean):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in ("'", '"'):
            if in_quote is None:
                in_quote = char
                q_start = i
            elif in_quote == char:
                in_quote = None
                quotes.append((q_start, i))

    def _is_in_quote(pos: int) -> bool:
        return any(s <= pos <= e for s, e in quotes)

    # Match LIMIT n or LIMIT offset, count (MySQL offset syntax)
    for m in re.finditer(r"[()]|\bLIMIT\s+\d+(?:\s*,\s*\d+)?\b", clean, re.IGNORECASE):
        if _is_in_quote(m.start()):
            continue

        tok = m.group()
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        elif depth == 0:
            last_limit_pos = m.start()
            last_limit_end = m.end()
            # For "LIMIT offset, count", count is the last number; for "LIMIT n", n is the count
            nums = re.findall(r"\d+", tok)
            existing_limit = int(nums[-1])
            existing_offset = int(nums[-2]) if len(nums) > 1 else None

    if existing_limit is not None:
        capped = min(existing_limit, limit)
        if existing_offset is not None:
            return clean[:last_limit_pos] + f"LIMIT {existing_offset}, {capped}" + clean[last_limit_end:]
        return clean[:last_limit_pos] + f"LIMIT {capped}" + clean[last_limit_end:]

    return clean + f" LIMIT {limit}"
