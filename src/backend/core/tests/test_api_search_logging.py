"""Tests for search API logging and redaction."""

import logging
import re
from unittest.mock import patch

import pytest
import responses
from rest_framework.test import APIClient

from .utils import build_authorization_bearer, setup_oicd_resource_server

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.django_db

# pylint: disable=redefined-outer-name


@pytest.fixture
def authenticated_client():
    """Return an authenticated API client."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}")
    return client


@responses.activate
@patch("core.views.search")
def test_search_view_does_not_log_raw_query(
    mock_search, caplog, authenticated_client, settings
):
    """Search endpoint should not log the raw query string."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    mock_search.return_value = {"hits": {"hits": []}}

    with caplog.at_level(logging.INFO, logger="core.views"):
        response = authenticated_client.post(
            "/api/v1.0/documents/search/",
            {"q": "leak_token_xyz"},
            format="json",
        )

    assert response.status_code == 200

    for record in caplog.records:
        assert "leak_token_xyz" not in record.message

    found_redacted = False
    for record in caplog.records:
        if "len=" in record.message and "hash=" in record.message:
            found_redacted = True
            break
    assert found_redacted, "Expected redacted query format in logs"


@responses.activate
@patch("core.views.search")
def test_search_view_logs_redacted_query_format(
    mock_search, caplog, authenticated_client, settings
):
    """Search endpoint should log query in redacted format.

    Expected format: 'Search query=len=X hash=XXXXXXXX on index'
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    mock_search.return_value = {"hits": {"hits": []}}

    with caplog.at_level(logging.INFO, logger="core.views"):
        response = authenticated_client.post(
            "/api/v1.0/documents/search/",
            {"q": "test_query"},
            format="json",
        )

    assert response.status_code == 200

    pattern = r"Search query=len=\d+ hash=[0-9a-f]{8} on index "
    found_match = False
    for record in caplog.records:
        if re.search(pattern, record.message):
            found_match = True
            break
    assert found_match, f"Expected log matching pattern '{pattern}' in logs"


@responses.activate
@patch("core.views.search")
def test_search_view_does_not_log_full_results_at_debug(
    mock_search, caplog, authenticated_client, settings
):
    """Search endpoint should not log full result bodies at DEBUG level."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    mock_search.return_value = {
        "hits": {"hits": [{"id": "DOC_BODY_LEAK", "title": "sensitive document"}]}
    }

    with caplog.at_level(logging.DEBUG, logger="core.views"):
        response = authenticated_client.post(
            "/api/v1.0/documents/search/",
            {"q": "test"},
            format="json",
        )

    assert response.status_code == 200

    for record in caplog.records:
        assert "DOC_BODY_LEAK" not in record.message


@responses.activate
@patch("core.views.search")
def test_search_view_still_logs_result_count(
    mock_search, caplog, authenticated_client, settings
):
    """Search endpoint should still log the result count at INFO level."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    mock_search.return_value = {"hits": {"hits": [{"id": "doc1", "title": "result"}]}}

    with caplog.at_level(logging.INFO, logger="core.views"):
        response = authenticated_client.post(
            "/api/v1.0/documents/search/",
            {"q": "test"},
            format="json",
        )

    assert response.status_code == 200

    pattern = r"found \d+ results"
    found_match = False
    for record in caplog.records:
        if re.search(pattern, record.message):
            found_match = True
            break
    assert found_match, f"Expected log matching pattern '{pattern}' in logs"
