import hashlib
import json
import logging
import os
from datetime import datetime, timezone

AUDIT_LOGGER_NAME = "mysql-audit"
_audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
_fallback_logger = logging.getLogger(__name__)

__all__ = ["log_query_event"]


def log_query_event(*, tool: str, sql: str, database: str | None, status: str = "success") -> None:
    # `user` reflects the DB connection credential (MYSQL_USER), not the MCP client identity.
    # MCP session identity is not resolvable from Context in v1 — known limitation, future enhancement.
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": os.getenv("MYSQL_USER", "unknown"),
        "tool": tool,
        "database": database or "",
        "query_hash": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        "status": status,
    }
    try:
        _audit_logger.info(json.dumps(event))
    except Exception:
        _fallback_logger.exception("audit.log_query_event failed to emit event")
