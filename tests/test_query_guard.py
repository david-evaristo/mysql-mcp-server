import logging

import pytest

from src.db.query_guard import (
    SqlParseValidator,
    WriteKeywordValidator,
    add_limit,
    validate_query,
)


class TestSqlParseValidator:
    def test_select_passes(self):
        SqlParseValidator.validate("SELECT * FROM t")

    def test_select_with_cte_passes(self):
        SqlParseValidator.validate("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_insert_blocked(self):
        with pytest.raises(ValueError, match=r"Only SELECT queries are allowed\."):
            SqlParseValidator.validate("INSERT INTO t VALUES (1)")

    def test_comment_does_not_fail_validation(self):
        # A valid SELECT with a leading comment should pass
        SqlParseValidator.validate("-- initial comment\nSELECT * FROM t")

    def test_trailing_comment_does_not_split_statement(self):
        # sqlparse keeps trailing comments attached to the preceding statement (no split).
        # "SELECT * FROM t; -- comment" counts as 1 statement (SELECT), not 2.
        SqlParseValidator.validate("SELECT * FROM t; -- just reading")

    def test_non_select_with_inline_comment_blocked(self):
        with pytest.raises(ValueError, match="Only SELECT"):
            SqlParseValidator.validate("DROP TABLE t; -- tricky")

    def test_multiple_statements_blocked(self):
        with pytest.raises(ValueError, match="Multiple statements are not allowed"):
            SqlParseValidator.validate("SELECT * FROM t; SELECT * FROM t2")

        with pytest.raises(ValueError, match="Multiple statements are not allowed"):
            SqlParseValidator.validate("SELECT * FROM t; DELETE FROM users")

    def test_empty_statement_blocked(self):
        with pytest.raises(ValueError, match="Query contains unparseable SQL syntax"):
            SqlParseValidator.validate("   ;  -- only comments and semicolons  ")

    def test_select_into_table_not_blocked_by_parse_validator(self):
        """SELECT INTO <table> is classified as SELECT by sqlparse — SqlParseValidator
        allows it to pass. This test documents that blocking comes from WriteKeywordValidator."""
        # SqlParseValidator alone does NOT block SELECT INTO — WriteKeywordValidator blocks it.
        # validate_query() runs both in sequence, so the combination blocks correctly.
        SqlParseValidator.validate("SELECT * INTO new_table FROM t")  # passes SqlParseValidator

    def test_parenthesized_select_blocked(self):
        """Parenthesized SELECT is classified as UNKNOWN by sqlparse — correctly blocked."""
        with pytest.raises(ValueError, match="unparseable SQL syntax"):
            SqlParseValidator.validate("(SELECT * FROM t)")

    def test_explain_analyze_blocked(self):
        """EXPLAIN ANALYZE is not SELECT — sqlparse classifies as UNKNOWN — blocked."""
        with pytest.raises(ValueError, match="unparseable SQL syntax"):
            SqlParseValidator.validate("EXPLAIN ANALYZE SELECT * FROM t")


class TestWriteKeywordValidator:
    def test_select_passes(self):
        WriteKeywordValidator().validate("SELECT * FROM t")

    def test_drop_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("DROP TABLE t")

    def test_comment_masking_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("SELECT 1 /* DROP TABLE t */")

    # --- CR-1: file I/O keywords ---
    def test_select_into_outfile_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("SELECT * FROM t INTO OUTFILE '/tmp/x.csv'")

    def test_select_into_dumpfile_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("SELECT * FROM t INTO DUMPFILE '/tmp/x.bin'")

    def test_load_data_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("LOAD DATA INFILE '/etc/passwd' INTO TABLE tmp")

    # --- CR-1: prepared statement bypass ---
    def test_execute_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("EXECUTE stmt")

    def test_prepare_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("PREPARE stmt FROM 'SELECT 1'")

    def test_deallocate_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("DEALLOCATE PREPARE stmt")

    # --- CR-1: DDL / admin ---
    def test_set_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("SET GLOBAL max_connections = 1")

    def test_rename_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("RENAME TABLE t TO t_bak")

    def test_flush_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("FLUSH TABLES")

    def test_kill_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("KILL CONNECTION 42")

    def test_shutdown_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("SHUTDOWN")

    def test_handler_blocked(self):
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("HANDLER t READ FIRST")

    def test_select_into_table_blocked(self):
        """SELECT INTO <table> is a write operation — creates table in PostgreSQL, assigns variable in MySQL."""
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("SELECT * INTO new_table FROM t")

    def test_select_into_variable_blocked(self):
        """SELECT ... INTO @var assigns variable — write operation in MySQL."""
        with pytest.raises(ValueError, match="write operation"):
            WriteKeywordValidator().validate("SELECT id INTO @result FROM t WHERE id = 1")


class TestAddLimit:
    def test_no_existing_limit_adds_limit(self):
        result = add_limit("SELECT * FROM t", 100)
        assert result == "SELECT * FROM t LIMIT 100"

    def test_existing_limit_higher_than_cap_is_capped(self):
        result = add_limit("SELECT * FROM t LIMIT 200", 100)
        assert result == "SELECT * FROM t LIMIT 100"

    def test_existing_limit_lower_than_cap_preserved(self):
        result = add_limit("SELECT * FROM t LIMIT 50", 100)
        assert result == "SELECT * FROM t LIMIT 50"

    def test_subquery_limit_not_modified(self):
        sql = "SELECT * FROM (SELECT id FROM t LIMIT 50) sub"
        result = add_limit(sql, 100)
        assert "LIMIT 50" in result
        assert result.endswith("LIMIT 100")

    def test_trailing_semicolon_stripped(self):
        result = add_limit("SELECT * FROM t;", 100)
        assert result == "SELECT * FROM t LIMIT 100"

    def test_limit_in_line_comment_is_not_treated_as_existing_limit(self):
        # "-- LIMIT 1000" é comentário — comentários devem ser removidos antes do parse
        result = add_limit("SELECT * FROM t -- LIMIT 1000", 500)
        assert "--" not in result  # comentário removido
        assert result.upper().endswith("LIMIT 500")

    def test_limit_in_block_comment_is_not_treated_as_existing_limit(self):
        result = add_limit("SELECT * FROM t /* LIMIT 1000 */", 500)
        assert result.upper().endswith("LIMIT 500")

    def test_limit_offset_count_syntax_is_capped(self):
        # LIMIT 0, 1000 → a contagem (1000) deve ser limitada a 500
        result = add_limit("SELECT * FROM t LIMIT 0, 1000", 500)
        assert "1000" not in result
        assert "500" in result

    def test_limit_offset_count_syntax_below_cap_preserved(self):
        result = add_limit("SELECT * FROM t LIMIT 0, 10", 500)
        assert "10" in result


class TestValidateQueryAuditLog:
    def test_blocked_query_logs_hash_not_sql(self, caplog):
        with caplog.at_level(logging.WARNING, logger="mysql-mcp.audit"):
            with pytest.raises(ValueError):
                validate_query("DROP TABLE users")

        assert len(caplog.records) == 1
        msg = caplog.records[0].getMessage()
        assert "DROP TABLE" not in msg
        assert "sql_sha256=" in msg
