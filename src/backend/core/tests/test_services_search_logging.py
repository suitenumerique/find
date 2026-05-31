"""Tests for search query redaction in services.search logging."""

import logging
import re

from core.services.search import get_query


class TestGetQueryLogging:
    """Test that get_query() redacts sensitive search queries in logs."""

    def test_get_query_does_not_log_raw_query_for_full_text(self, caplog):
        """Full-text search should not log the raw query string."""
        with caplog.at_level(logging.INFO, logger="core.services.search"):
            get_query(
                q="leak_secret_xyz",
                reach="all",
                visited=[],
                user_sub="user123",
                groups=[],
                tags=[],
                path=None,
            )

        # Assert no record contains the raw secret
        for record in caplog.records:
            assert "leak_secret_xyz" not in record.message

        # Assert at least one record contains redaction format (len= and hash=)
        messages = [r.message for r in caplog.records]
        assert any("len=" in msg and "hash=" in msg for msg in messages)

    def test_get_query_match_all_log_unchanged(self, caplog):
        """Wildcard query should log the unchanged match_all message."""
        with caplog.at_level(logging.INFO, logger="core.services.search"):
            get_query(
                q="*",
                reach="all",
                visited=[],
                user_sub="user123",
                groups=[],
                tags=[],
                path=None,
            )

        # Assert exactly one INFO record with the match_all message
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        msg_list = [r.message for r in info_records]
        assert len(info_records) == 1, (
            f"Expected exactly 1 INFO record, got {len(info_records)}: {msg_list}"
        )
        assert info_records[0].message == "Performing match_all query", (
            f"Wrong message: {info_records[0].message!r}"
        )

    def test_get_query_full_text_log_uses_redaction_format(self, caplog):
        """Full-text search should log redacted format: len=N hash=XXXXXXXX."""
        with caplog.at_level(logging.INFO, logger="core.services.search"):
            get_query(
                q="someuserquery",
                reach="all",
                visited=[],
                user_sub="user123",
                groups=[],
                tags=[],
                path=None,
            )

        # Assert at least one record matches the redaction format
        pattern = r"Performing full-text search: len=\d+ hash=[0-9a-f]{8}"
        messages = [r.message for r in caplog.records]
        assert any(re.search(pattern, msg) for msg in messages), (
            f"No message matched pattern {pattern}. Got: {messages}"
        )
