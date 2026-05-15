"""Fixtures for tests in the find core application"""

import json
import re
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from django.conf import LazySettings

import pytest
from django_bolt.testing import TestClient
from faker import Faker
from opensearchpy.exceptions import NotFoundError
from vcr.request import Request

from core import bolt_auth, handlers
from core.authentication import ResourceUser
from core.handlers import api
from core.services import opensearch

fake = Faker()
Faker.seed(12345)


@pytest.fixture
def bolt_client() -> Generator[TestClient, None, None]:
    bolt_auth._get_resource_server_backend.cache_clear()
    with TestClient(api) as client:
        yield client
    bolt_auth._get_resource_server_backend.cache_clear()


@pytest.fixture
def mock_oidc_user() -> Generator[ResourceUser, None, None]:
    """Mock OIDC user for handler tests.

    Patches _require_oidc_user to return a mock user with sub='test-user-123'.
    Use this instead of @responses.activate + setup_oicd_resource_server since
    Bolt's Rust/Python bridge doesn't propagate responses mocking correctly.
    """
    user = ResourceUser(sub="test-user-123")
    user.token_audience = "test-audience"

    with patch.object(handlers, "_require_oidc_user", new=AsyncMock(return_value=user)):
        yield user


@pytest.fixture
def mock_service_context() -> Generator[dict, None, None]:
    """Mock service context for handler tests.

    Patches _require_service_context to return a mock service context.
    """
    context = {"service_id": 1, "service_name": "test-service"}

    with patch.object(
        handlers, "_require_service_context", new=AsyncMock(return_value=context)
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
    """Randomize index name per test; cleanup real indices for integration tests only."""
    using_mock = "mock_opensearch_client" in request.fixturenames
    is_integration = "integration" in request.keywords

    original_index = settings.OPENSEARCH_INDEX
    test_index = "".join(fake.random_letters(5)).lower()
    settings.OPENSEARCH_INDEX = test_index

    client = None
    if is_integration and not using_mock:
        client = opensearch.opensearch_client()

    yield

    settings.OPENSEARCH_INDEX = original_index

    if client is not None:
        try:
            client.indices.delete(index=test_index)
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

    # Normalize index name in path
    request.uri = re.sub(r"(https?://[^/]+)/[^/]+/", r"\1/test-index/", request.uri)

    # Normalize document ID (UUID pattern in _doc/{id} paths)
    request.uri = re.sub(
        r"/_doc/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/_doc/test-doc-id",
        request.uri,
    )

    # Normalize timestamps in request body for deterministic matching
    if request.body:
        try:
            body = request.body
            if isinstance(body, bytes):
                body = body.decode("utf-8")

            # Normalize ISO timestamps (e.g., 2026-05-13T15:44:30.258378+00:00)
            body = re.sub(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+\d{2}:\d{2}|Z)?",
                "2020-01-01T00:00:00+00:00",
                body,
            )

            request.body = body
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass  # Leave body as-is if we can't parse it

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
