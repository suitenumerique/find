"""Tests for the DSL-based search API endpoint POST /api/v1.0/documents/search/"""

import pytest
import responses
from rest_framework.test import APIClient

from .utils import build_authorization_bearer, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


class TestSearchDSLAnonymous:
    """Tests for anonymous access to DSL search endpoint."""

    def test_anonymous_request_denied(self):
        """Anonymous requests should return 401."""
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {"query": "test"},
            format="json",
        )
        assert response.status_code == 401


class TestSearchDSLBasicQuery:
    """Tests for basic DSL query functionality."""

    @responses.activate
    def test_basic_query_string(self, settings, mock_opensearch_client):
        """Test basic query with just a query string."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {"query": "test search"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        mock_opensearch_client.search.assert_called_once()

    @responses.activate
    def test_match_all_query(self, settings, mock_opensearch_client):
        """Test match_all query with asterisk."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {"query": "*"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200

    @responses.activate
    def test_null_query_uses_match_all(self, settings, mock_opensearch_client):
        """Test that null/missing query uses match_all."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {"query": None},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200


class TestSearchDSLWhereClause:
    """Tests for DSL where clause filtering."""

    @responses.activate
    def test_where_eq_filter(self, settings, mock_opensearch_client):
        """Test where clause with eq operator."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "query": "*",
                "where": {"field": "reach", "op": "eq", "value": "public"},
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200

    @responses.activate
    def test_where_and_clause(self, settings, mock_opensearch_client):
        """Test where clause with AND combinator."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "query": "*",
                "where": {
                    "and": [
                        {"field": "reach", "op": "eq", "value": "public"},
                        {"field": "tags", "op": "in", "value": ["important"]},
                    ]
                },
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200

    @responses.activate
    def test_where_or_clause(self, settings, mock_opensearch_client):
        """Test where clause with OR combinator."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "query": "*",
                "where": {
                    "or": [
                        {"field": "reach", "op": "eq", "value": "public"},
                        {"field": "reach", "op": "eq", "value": "authenticated"},
                    ]
                },
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200

    @responses.activate
    def test_where_not_clause(self, settings, mock_opensearch_client):
        """Test where clause with NOT combinator."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "query": "*",
                "where": {
                    "not": {"field": "reach", "op": "eq", "value": "restricted"}
                },
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200


class TestSearchDSLSortAndLimit:
    """Tests for sort and limit parameters."""

    @responses.activate
    def test_sort_by_created_at(self, settings, mock_opensearch_client):
        """Test sorting by created_at field."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "query": "*",
                "sort": [{"field": "created_at", "direction": "desc"}],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200

    @responses.activate
    def test_limit_parameter(self, settings, mock_opensearch_client):
        """Test limit parameter."""
        setup_oicd_resource_server(responses, settings, sub="user_sub")
        mock_opensearch_client.search.return_value = {"hits": {"hits": []}}

        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "query": "*",
                "limit": 10,
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        # Verify limit was passed to OpenSearch
        call_args = mock_opensearch_client.search.call_args
        assert call_args[1]["body"]["size"] == 10
