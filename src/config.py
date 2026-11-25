"""
Centralised configuration — reads environment variables exactly once.
Isolates the rest of the code from os.environ (DIP / SRP).
"""
import os
import warnings
from dataclasses import dataclass

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def _int_env(name: str, default: str) -> int:
    """Read an environment variable as an integer; fails early with a clear message on bad values."""
    val = os.getenv(name, default)
    try:
        return int(val)
    except ValueError as err:
        raise ValueError(f"Invalid value for {name}: {val!r}. Expected an integer.") from err


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Immutable configuration read once from the environment.

    Authentication is fully delegated to the Teleport proxy (mTLS certificate),
    so there is no password field — the connection requires no explicit credential.
    """

    host: str
    port: int
    user: str
    max_rows: int = 500
    pool_minsize: int = 2
    pool_maxsize: int = 10
    connect_timeout: int = 10
    query_timeout: int = 30
    rate_limit: int = 60  # Max tool calls per minute; 0 = disabled

    def __repr__(self) -> str:
        return (
            f"DatabaseConfig(host={self.host!r}, port={self.port}, "
            f"user={self.user!r}, max_rows={self.max_rows})"
        )

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """
        Build the configuration from environment variables.

        Emits a ``UserWarning`` if ``MYSQL_HOST`` is not a loopback address,
        because the architecture requires the Teleport proxy to run locally.
        """
        host = os.getenv("MYSQL_HOST")
        user = os.getenv("MYSQL_USER")
        if not host or not host.strip():
            raise ValueError("Environment variable MYSQL_HOST is not set or empty.")
        if not user or not user.strip():
            raise ValueError("Environment variable MYSQL_USER is not set or empty.")
        host = host.strip()
        user = user.strip()
        if host not in _LOOPBACK:
            warnings.warn(
                f"MYSQL_HOST={host!r} is not a loopback address. "
                "This server expects a Teleport Database Access tunnel — run "
                "'tsh db login <db-name> --db-user=<role>' followed by "
                "'tsh proxy db --tunnel --port=<port>' and set MYSQL_HOST=127.0.0.1 "
                "to avoid unencrypted direct connections.",
                stacklevel=2,
            )

        return cls(
            host=host,
            port=_int_env("MYSQL_PORT", "54855"),
            user=user,
            max_rows=_int_env("MCP_MAX_ROWS", "500"),
            pool_minsize=_int_env("MCP_POOL_MIN", "2"),
            pool_maxsize=_int_env("MCP_POOL_MAX", "10"),
            connect_timeout=_int_env("MCP_CONNECT_TIMEOUT", "10"),
            query_timeout=_int_env("MCP_QUERY_TIMEOUT", "30"),
            rate_limit=_int_env("MCP_RATE_LIMIT", "60"),
        )


def get_transport() -> str:
    """Return the MCP transport mode; raises ``ValueError`` for unrecognised values."""
    transport = os.getenv("MCP_TRANSPORT", "http").strip().lower()
    if transport not in ("http", "stdio"):
        raise ValueError(f"Invalid MCP_TRANSPORT {transport!r}. Expected 'http' or 'stdio'.")
    return transport
