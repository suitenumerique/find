"""Fixtures for tests in the find core application"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from django.conf import LazySettings

import pytest
from django_bolt.testing import TestClient
from opensearchpy.exceptions import NotFoundError
from vcr.request import Request

from core import bolt_auth, handlers, middleware
from core.authentication import ResourceUser
from core.handlers import api
from core.services import opensearch
from core.services.indexing import ensure_index_exists

TEST_INDEX = "test-index"


@pytest.fixture
def bolt_client() -> Generator[TestClient, None, None]:
    bolt_auth._get_resource_server_backend.cache_clear()
    with TestClient(api) as client:
        yield client
    bolt_auth._get_resource_server_backend.cache_clear()


@pytest.fixture
def mock_oidc_user() -> Generator[ResourceUser, None, None]:
    """Mock OIDC user for handler tests via SearchAuthMiddleware."""
    user = ResourceUser(sub="test-user-123")
    user.token_audience = "test-audience"

    async def mock_process_request(self, request):
        request.state["user"] = user
        return await self.get_response(request)

    with patch.object(
        middleware.SearchAuthMiddleware, "process_request", mock_process_request
    ):
        yield user


@pytest.fixture
def mock_service_context() -> Generator[dict, None, None]:
    """Mock service context for handler tests via ServiceAuthMiddleware."""
    context = {"service_name": "test_service", "client_id": "test_client"}

    async def mock_process_request(self, request):
        request.state["service_name"] = context["service_name"]
        request.state["client_id"] = context["client_id"]
        return await self.get_response(request)

    with patch.object(
        middleware.ServiceAuthMiddleware, "process_request", mock_process_request
    ):
        yield context


@pytest.fixture
def mock_search_service_auth() -> Generator[dict, None, None]:
    """Mock service auth for search endpoint via SearchAuthMiddleware."""
    context = {"service_name": "test_service", "client_id": "test_client"}

    async def mock_process_request(self, request):
        request.state["service_name"] = context["service_name"]
        request.state["client_id"] = context["client_id"]
        return await self.get_response(request)

    with patch.object(
        middleware.SearchAuthMiddleware, "process_request", mock_process_request
    ):
        yield context


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Force integration tests to run on a single worker (serial execution)."""
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(pytest.mark.xdist_group("integration"))


@pytest.fixture
def mock_opensearch_client():
    """
    Fixture that patches core.services.opensearch.opensearch_client with a MagicMock.

    Handles the @cache decorator by calling cache_clear() before and after the test.

    Usage:
        def test_something(mock_opensearch_client):
            mock_opensearch_client.search.return_value = {"hits": {"hits": [], "total": 1}}
            # ... test code ...
    """
    mock_client = MagicMock()

    opensearch.opensearch_client.cache_clear()
    with patch.object(opensearch, "opensearch_client", return_value=mock_client):
        yield mock_client
    opensearch.opensearch_client.cache_clear()


@pytest.fixture(autouse=True)
def cleanup_test_index(settings: LazySettings, request: pytest.FixtureRequest) -> None:
    """Set fixed index name and ensure index exists for VCR recording."""
    original_index = settings.OPENSEARCH_INDEX
    settings.OPENSEARCH_INDEX = TEST_INDEX

    ensure_index_exists(TEST_INDEX)

    yield

    settings.OPENSEARCH_INDEX = original_index

    try:
        opensearch.opensearch_client().indices.delete(index=TEST_INDEX)
    except NotFoundError:
        pass


def redact_opensearch_request(request: Request) -> Request:
    """Normalize OpenSearch requests for deterministic VCR matching."""
    if request.host not in ("localhost", "opensearch") or request.port != 9200:
        return request

    if "authorization" in request.headers:
        request.headers["authorization"] = "<REDACTED>"
    if "user-agent" in request.headers:
        request.headers["user-agent"] = "opensearch-py/x.y.z (Python x.y.z)"

    return request


def redact_opensearch_response(response: dict[str, Any]) -> dict[str, Any]:
    """Redact environment-specific headers from OpenSearch responses."""
    if "X-OpenSearch-Version" in response["headers"]:
        response["headers"]["X-OpenSearch-Version"] = ["OpenSearch/x.y.z (opensearch)"]
    return response


@pytest.fixture(scope="module")
def vcr_config():
    """VCR configuration for recording HTTP interactions with OpenSearch."""
    return {
        "cassette_library_dir": "core/tests/cassettes",
        "record_mode": "once",
        "match_on": ["method", "scheme", "host", "port", "path", "query", "body"],
        "decode_compressed_response": True,
        "before_record_request": redact_opensearch_request,
        "before_record_response": redact_opensearch_response,
    }
