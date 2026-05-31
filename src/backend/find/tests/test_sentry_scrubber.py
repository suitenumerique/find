"""Tests for Sentry event scrubbing."""

from find.sentry_scrubber import before_send


def test_before_send_returns_none_when_event_is_none():
    """None events should be passed through."""
    assert before_send(None, {}) is None


def test_before_send_handles_missing_request_key():
    """Events without request metadata should be unchanged."""
    event = {}

    assert before_send(event, {}) == event


def test_before_send_strips_authorization_header():
    """Authorization headers should be removed while preserving other headers."""
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer abc123",
                "Content-Type": "application/json",
            }
        }
    }

    result = before_send(event, {})

    assert result is not None
    assert "Authorization" not in result["request"]["headers"]
    assert result["request"]["headers"]["Content-Type"] == "application/json"


def test_before_send_handles_missing_authorization_header():
    """Headers without Authorization should be unchanged."""
    event = {"request": {"headers": {"Content-Type": "application/json"}}}

    assert before_send(event, {}) == event


def test_before_send_strips_request_data_unconditionally():
    """Request bodies should be replaced wholesale."""
    event = {"request": {"data": {"username": "u", "password": "p"}}}

    result = before_send(event, {})

    assert result is not None
    assert result["request"]["data"] == "[Filtered]"


def test_before_send_strips_request_data_multipart():
    """Multipart-looking request bodies should also be replaced wholesale."""
    event = {"request": {"data": {"file": "<file>", "name": "test"}}}

    result = before_send(event, {})

    assert result is not None
    assert result["request"]["data"] == "[Filtered]"


def test_before_send_redacts_token_query_param():
    """Token-bearing query string values should be redacted only where needed."""
    event = {"request": {"query_string": "token=abc123&q=search"}}

    result = before_send(event, {})

    assert result is not None
    assert "q=search" in result["request"]["query_string"]
    assert "abc123" not in result["request"]["query_string"]


def test_before_send_handles_missing_query_string():
    """Requests without query strings should be unchanged."""
    event = {"request": {"headers": {}}}

    assert before_send(event, {}) == event


def test_before_send_preserves_unrelated_fields():
    """Unrelated top-level Sentry fields should be preserved."""
    event = {
        "request": {},
        "tags": {"service": "find"},
        "extra": {"feature": "search"},
        "level": "error",
    }

    result = before_send(event, {})

    assert result is not None
    assert result["tags"] == {"service": "find"}
    assert result["extra"] == {"feature": "search"}
    assert result["level"] == "error"
