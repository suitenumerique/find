"""Fixtures for tests in the find demo application"""

import pytest

from core.tests.conftest import redact_opensearch_request, redact_opensearch_response


@pytest.fixture(scope="module")
def vcr_config():
    """VCR configuration for recording HTTP interactions with OpenSearch."""
    return {
        "cassette_library_dir": "demo/tests/cassettes",
        "record_mode": "once",
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
        "decode_compressed_response": True,
        "before_record_request": redact_opensearch_request,
        "before_record_response": redact_opensearch_response,
    }
