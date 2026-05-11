"""Fixtures for unit tests - no OpenSearch connection required."""

import pytest


@pytest.fixture(autouse=True)
def mock_opensearch_for_unit_tests(mock_opensearch_client):
    """Auto-use mock_opensearch_client for all unit tests.

    This ensures the cleanup_test_index fixture from the parent conftest.py
    detects that mocking is active and skips real OpenSearch operations.
    """
    yield mock_opensearch_client
