"""Fixtures for tests in the find core application"""

from unittest.mock import MagicMock, patch

from django.conf import LazySettings

import pytest
from faker import Faker
from opensearchpy.exceptions import NotFoundError

from core import views
from core.services import indexing, opensearch

fake = Faker()


@pytest.fixture
def mock_opensearch_client():
    """
    Fixture that patches core.services.opensearch.opensearch_client with a MagicMock.

    Handles the @cache decorator by calling cache_clear() before patching.
    Provides sensible default return values for all common OpenSearch operations.

    Usage:
        def test_something(mock_opensearch_client):
            mock_opensearch_client.search.return_value = {"hits": {"hits": [...], "total": {"value": 1}}}
            # ... test code ...
    """
    # Clear the cache to ensure we patch the actual function, not a cached result
    opensearch.opensearch_client.cache_clear()

    mock_client = MagicMock()

    # Configure default return values for self-tests and health checks
    mock_client.ping.return_value = True
    mock_client.cluster.health.return_value = {"status": "green"}

    # Configure default return values for index operations
    mock_client.indices.get.return_value = {}
    mock_client.indices.create.return_value = {"acknowledged": True}
    mock_client.indices.delete.return_value = {"acknowledged": True}
    mock_client.indices.refresh.return_value = {"_shards": {"successful": 1}}
    mock_client.indices.exists.return_value = False

    # Configure default return values for document operations
    mock_client.search.return_value = {
        "hits": {"hits": [], "total": {"value": 0}},
        "took": 1,
        "timed_out": False,
    }
    mock_client.index.return_value = {"_id": "test_id", "result": "created"}
    mock_client.bulk.return_value = {"items": [], "errors": False}
    mock_client.delete_by_query.return_value = {"deleted": 0}
    mock_client.get.return_value = {"_id": "test_id", "_source": {}}
    mock_client.count.return_value = {"count": 0}

    with (
        patch.object(opensearch, "opensearch_client", return_value=mock_client),
        patch.object(views, "opensearch_client", return_value=mock_client),
        patch.object(indexing, "opensearch_client", return_value=mock_client),
    ):
        yield mock_client

    # Clear cache again after test to ensure clean state for next test
    opensearch.opensearch_client.cache_clear()


@pytest.fixture(autouse=True)
def cleanup_test_index(settings: LazySettings, request: pytest.FixtureRequest) -> None:
    """
    Fixture to set a randomized index name for tests and remove it on tear down.

    When mock_opensearch_client fixture is active, this fixture skips real
    OpenSearch operations and only manages the settings.
    """
    # Check if mock_opensearch_client is being used in this test
    using_mock = "mock_opensearch_client" in request.fixturenames

    original_index = settings.OPENSEARCH_INDEX
    test_index = "".join(fake.random_letters(5)).lower()
    settings.OPENSEARCH_INDEX = test_index

    client = None
    if not using_mock:
        # Create client here to prevent "teardown" issues when the opensearch settings are
        # removed for error tests.
        client = opensearch.opensearch_client()

    yield

    settings.OPENSEARCH_INDEX = original_index

    if not using_mock and client is not None:
        try:
            client.indices.delete(index=test_index)
        except NotFoundError:
            pass
