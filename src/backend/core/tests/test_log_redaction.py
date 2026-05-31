"""Tests for log_redaction module."""

import re

from core.log_redaction import redact_search_query


class TestRedactSearchQuery:
    """Test suite for redact_search_query function."""

    def test_redact_search_query_format(self):
        r"""Output matches regex ^len=\d+ hash=[0-9a-f]{8}$"""
        result = redact_search_query("test query")
        pattern = r"^len=\d+ hash=[0-9a-f]{8}$"
        assert re.match(pattern, result), (
            f"Output '{result}' does not match pattern '{pattern}'"
        )

    def test_redact_search_query_does_not_contain_input(self):
        """Input john.doe@example.com not in output"""
        sensitive_input = "john.doe@example.com"
        result = redact_search_query(sensitive_input)
        assert sensitive_input not in result, (
            f"Sensitive input found in output: {result}"
        )

    def test_redact_search_query_empty_string(self):
        """No exception raised; output is exactly len=0 hash=e3b0c442"""
        result = redact_search_query("")
        assert result == "len=0 hash=e3b0c442", (
            f"Expected 'len=0 hash=e3b0c442', got '{result}'"
        )

    def test_redact_search_query_deterministic(self):
        """redact_search_query("foo") == redact_search_query("foo")"""
        result1 = redact_search_query("foo")
        result2 = redact_search_query("foo")
        assert result1 == result2, f"Non-deterministic: '{result1}' != '{result2}'"

    def test_redact_search_query_different_inputs_differ(self):
        """redact_search_query("foo") != redact_search_query("bar")"""
        result_foo = redact_search_query("foo")
        result_bar = redact_search_query("bar")
        assert result_foo != result_bar, (
            f"Different inputs produced same output: {result_foo}"
        )

    def test_redact_search_query_handles_unicode(self):
        """Input こんにちは does not raise; output matches format regex"""
        result = redact_search_query("こんにちは")
        pattern = r"^len=\d+ hash=[0-9a-f]{8}$"
        assert re.match(pattern, result), f"Unicode input failed: '{result}'"

    def test_redact_search_query_handles_whitespace(self):
        """Input '   ' produces len=3 hash=..."""
        result = redact_search_query("   ")
        assert result.startswith("len=3 hash="), (
            f"Whitespace handling failed: '{result}'"
        )
