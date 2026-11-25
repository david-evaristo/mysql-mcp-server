# tests/integration/test_security.py
"""
Integration tests for security validation.
Confirms that write keywords are blocked even against a real database.
"""
import pytest

from src.db.secure_repository import SecureQueryRepository


pytestmark = pytest.mark.integration


class TestSecurityAgainstRealDb:
    async def test_drop_table_blocked(self, query_repo: SecureQueryRepository):
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query("DROP TABLE t")

    async def test_insert_blocked(self, query_repo: SecureQueryRepository):
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query("INSERT INTO t VALUES (1)")

    async def test_update_blocked(self, query_repo: SecureQueryRepository):
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query("UPDATE t SET x=1")

    async def test_delete_blocked(self, query_repo: SecureQueryRepository):
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query("DELETE FROM t")

    async def test_truncate_blocked(self, query_repo: SecureQueryRepository):
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query("TRUNCATE TABLE t")

    async def test_create_blocked(self, query_repo: SecureQueryRepository):
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query("CREATE TABLE t (id INT)")

    async def test_comment_hidden_drop_blocked(
        self, query_repo: SecureQueryRepository
    ):
        # DROP hidden in a comment must not pass
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query("SELECT 1 /* DROP TABLE t */")

    async def test_invalid_identifier_blocked(
        self, query_repo: SecureQueryRepository
    ):
        with pytest.raises(ValueError, match="Invalid identifier"):
            await query_repo.execute_query("SELECT 1", database="db;malicious")

    async def test_valid_select_passes(
        self, query_repo: SecureQueryRepository
    ):
        result = await query_repo.execute_query("SELECT 1 AS ok")
        assert result["rows"][0]["ok"] == 1

    @pytest.mark.parametrize("sql", [
        "ALTER TABLE t ADD COLUMN x INT",
        "REPLACE INTO t VALUES (1)",
        "CALL my_proc()",
        "GRANT SELECT ON db.* TO user",
        "LOCK TABLES t READ",
    ])
    async def test_additional_write_keywords_blocked(
        self, query_repo: SecureQueryRepository, sql: str
    ):
        with pytest.raises(ValueError, match="write operation"):
            await query_repo.execute_query(sql)
