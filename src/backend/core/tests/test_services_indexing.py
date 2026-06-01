"""Tests for core.services.indexing helpers."""

from unittest.mock import MagicMock, patch

import pytest
from opensearchpy.exceptions import NotFoundError, RequestError

from core import factories
from core.services.indexing import (
    ensure_index_exists,
    get_all_active_service_indices,
    get_service_index_name,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cleanup_test_index():
    """Override parent conftest fixture: indexing tests manage their own indices."""
    yield


def test_get_service_index_name_prefixes(settings):
    """Index name is {prefix}-{service_slug}."""
    settings.OPENSEARCH_INDEX_PREFIX = "find"
    assert get_service_index_name("docs") == "find-docs"


def test_get_all_active_service_indices_filters_inactive(settings):
    """Only active services are included in the index list."""
    settings.OPENSEARCH_INDEX_PREFIX = "find"
    factories.ServiceFactory(slug="svca", is_active=True)
    factories.ServiceFactory(slug="svcb", is_active=True)
    factories.ServiceFactory(slug="svcc", is_active=False)
    indices = get_all_active_service_indices()
    assert len(indices) == 2
    assert "find-svca" in indices
    assert "find-svcb" in indices


def test_get_all_active_service_indices_empty(settings):
    """Empty list returned when no active services exist."""
    settings.OPENSEARCH_INDEX_PREFIX = "find"
    factories.ServiceFactory(is_active=False)
    assert get_all_active_service_indices() == []


def test_ensure_index_exists_idempotent_under_race():
    """ensure_index_exists handles race condition without raising."""
    mock_client = MagicMock()
    mock_client.indices.get.side_effect = NotFoundError(
        404, "index_not_found_exception", {}
    )
    mock_client.indices.create.side_effect = RequestError(
        400, "resource_already_exists_exception", {}
    )
    with patch("core.services.indexing.opensearch_client", return_value=mock_client):
        ensure_index_exists("test-idx")
