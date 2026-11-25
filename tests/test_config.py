"""Tests for src/config.py — DatabaseConfig construction and validation."""
import pytest

from src.config import DatabaseConfig


class TestDatabaseConfigFromEnv:
    """``DatabaseConfig.from_env`` reads env vars and validates required fields."""
    def test_all_required_vars_creates_config(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "myuser")
        monkeypatch.delenv("MYSQL_PORT", raising=False)

        cfg = DatabaseConfig.from_env()

        assert cfg.host == "127.0.0.1"
        assert cfg.user == "myuser"
        assert cfg.port == 54855

    def test_missing_host_raises(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "")
        monkeypatch.setenv("MYSQL_USER", "u")

        with pytest.raises(ValueError, match="MYSQL_HOST"):
            DatabaseConfig.from_env()

    def test_missing_user_raises(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "")

        with pytest.raises(ValueError, match="MYSQL_USER"):
            DatabaseConfig.from_env()

    def test_non_loopback_host_warns(self, monkeypatch):
        # Direct connections bypass the Teleport Database Access tunnel — the warning
        # guards against misconfiguration.
        monkeypatch.setenv("MYSQL_HOST", "rds.example.com")
        monkeypatch.setenv("MYSQL_USER", "u")

        with pytest.warns(UserWarning, match="not a loopback address"):
            DatabaseConfig.from_env()

    def test_non_loopback_host_warning_references_teleport_tunnel_command(self, monkeypatch):
        # The warning must point at the real Teleport Database Access commands
        # ('tsh db login' + 'tsh proxy db --tunnel'), not a generic message.
        monkeypatch.setenv("MYSQL_HOST", "rds.example.com")
        monkeypatch.setenv("MYSQL_USER", "u")

        with pytest.warns(UserWarning, match=r"tsh db login.*tsh proxy db --tunnel"):
            DatabaseConfig.from_env()

    def test_optional_vars_use_defaults(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "u")
        for key in ["MCP_MAX_ROWS", "MCP_POOL_MIN", "MCP_POOL_MAX",
                    "MCP_CONNECT_TIMEOUT", "MCP_QUERY_TIMEOUT", "MCP_RATE_LIMIT"]:
            monkeypatch.delenv(key, raising=False)

        cfg = DatabaseConfig.from_env()

        assert cfg.max_rows == 500
        assert cfg.pool_minsize == 2
        assert cfg.pool_maxsize == 10
        assert cfg.connect_timeout == 10
        assert cfg.query_timeout == 30
        assert cfg.rate_limit == 60

    def test_optional_vars_are_overridable(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.setenv("MCP_MAX_ROWS", "100")
        monkeypatch.setenv("MCP_POOL_MIN", "5")
        monkeypatch.setenv("MCP_POOL_MAX", "20")

        cfg = DatabaseConfig.from_env()

        assert cfg.max_rows == 100
        assert cfg.pool_minsize == 5
        assert cfg.pool_maxsize == 20

    def test_custom_port(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.setenv("MYSQL_PORT", "3307")

        cfg = DatabaseConfig.from_env()

        assert cfg.port == 3307

    def test_mysql_password_is_ignored(self, monkeypatch):
        # Auth is delegated to Teleport mTLS — no password field exists on DatabaseConfig.
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.setenv("MYSQL_PASSWORD", "s3cr3t")

        cfg = DatabaseConfig.from_env()

        assert cfg.host == "127.0.0.1"
        assert cfg.user == "u"
        assert not hasattr(cfg, "password")


class TestDatabaseConfigRepr:
    """``__repr__`` exposes host and user for debugging without leaking secrets."""
    def test_repr_contains_host_and_user(self):
        cfg = DatabaseConfig(host="myhost", port=54855, user="myuser")

        r = repr(cfg)

        assert "myhost" in r
        assert "myuser" in r


class TestDatabaseConfigRateLimit:
    """``rate_limit`` controls the MCP tool-call throttle; 0 disables it entirely."""
    def test_rate_limit_default_is_60(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.delenv("MCP_RATE_LIMIT", raising=False)

        cfg = DatabaseConfig.from_env()

        assert cfg.rate_limit == 60

    def test_rate_limit_is_configurable(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.setenv("MCP_RATE_LIMIT", "120")

        cfg = DatabaseConfig.from_env()

        assert cfg.rate_limit == 120

    def test_rate_limit_zero_disables_limiting(self, monkeypatch):
        monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.setenv("MCP_RATE_LIMIT", "0")

        cfg = DatabaseConfig.from_env()

        assert cfg.rate_limit == 0
