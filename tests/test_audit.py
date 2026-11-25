import hashlib
import json
import logging

import pytest

from src.audit import log_query_event


class TestLogQueryEventFields:
    def test_all_required_fields_present(self, caplog):
        with caplog.at_level(logging.INFO, logger="mysql-audit"):
            log_query_event(tool="execute_query", sql="SELECT 1", database="mydb")

        assert len(caplog.records) == 1
        event = json.loads(caplog.records[0].message)
        assert "timestamp" in event
        assert event["tool"] == "execute_query"
        assert event["database"] == "mydb"
        assert "query_hash" in event
        assert "user" in event

    def test_query_hash_is_sha256(self, caplog):
        sql = "SELECT * FROM users"
        with caplog.at_level(logging.INFO, logger="mysql-audit"):
            log_query_event(tool="execute_query", sql=sql, database="mydb")

        event = json.loads(caplog.records[0].message)
        expected = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        assert event["query_hash"] == expected

    def test_database_none_emits_empty_string(self, caplog):
        with caplog.at_level(logging.INFO, logger="mysql-audit"):
            log_query_event(tool="execute_query", sql="SELECT 1", database=None)

        event = json.loads(caplog.records[0].message)
        assert event["database"] == ""


class TestAuditUser:
    def test_user_from_env(self, caplog, monkeypatch):
        monkeypatch.setenv("MYSQL_USER", "alice")
        with caplog.at_level(logging.INFO, logger="mysql-audit"):
            log_query_event(tool="execute_query", sql="SELECT 1", database=None)

        event = json.loads(caplog.records[0].message)
        assert event["user"] == "alice"

    def test_user_defaults_to_unknown(self, caplog, monkeypatch):
        monkeypatch.delenv("MYSQL_USER", raising=False)
        with caplog.at_level(logging.INFO, logger="mysql-audit"):
            log_query_event(tool="execute_query", sql="SELECT 1", database=None)

        event = json.loads(caplog.records[0].message)
        assert event["user"] == "unknown"


class TestAuditSilentOnFailure:
    def test_logger_exception_does_not_propagate(self, monkeypatch):
        def broken_logger(*args, **kwargs):
            raise RuntimeError("broken")

        monkeypatch.setattr("src.audit._audit_logger.info", broken_logger)
        # Must not raise
        log_query_event(tool="execute_query", sql="SELECT 1", database="mydb")
