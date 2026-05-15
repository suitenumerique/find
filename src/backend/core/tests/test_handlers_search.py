from unittest.mock import MagicMock

import pytest
from django_bolt.testing import TestClient

from core.authentication import ResourceUser

pytestmark = pytest.mark.django_db


class TestSearchDocumentsHandler:
    @pytest.mark.vcr
    def test_search_simple_query_returns_200(
        self,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={"query": "test", "limit": 10},
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 200
        assert response.json() == {"data": [], "total": 0, "limit": 10}

    @pytest.mark.vcr
    def test_search_with_where_clause_returns_200(
        self,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={
                "query": "test",
                "where": {
                    "and": [{"field": "tags", "op": "in", "value": ["tag1", "tag2"]}]
                },
                "limit": 10,
            },
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 200
        assert response.json() == {"data": [], "total": 0, "limit": 10}

    @pytest.mark.vcr
    def test_search_with_sort_and_limit_returns_200(
        self,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={
                "query": "test",
                "sort": [{"field": "created_at", "direction": "desc"}],
                "limit": 5,
            },
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 200
        assert response.json() == {"data": [], "total": 0, "limit": 5}

    def test_search_missing_auth_returns_401(self, bolt_client: TestClient) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={"query": "test", "limit": 10},
        )

        assert response.status_code == 401

    def test_search_malformed_auth_header_returns_401(
        self, bolt_client: TestClient
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={"query": "test", "limit": 10},
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )

        assert response.status_code == 401

    def test_search_invalid_dsl_structure_returns_422(
        self,
        mock_opensearch_client: MagicMock,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={
                "query": "test",
                "where": {"field": "tags"},
                "limit": 10,
            },
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body"],
                    "msg": "Invalid where clause: {'field': 'tags'}",
                    "type": "validation_error",
                }
            ]
        }

    def test_search_invalid_json_returns_422(
        self,
        mock_opensearch_client: MagicMock,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            content=b"not valid json {{{",
            headers={
                "Authorization": "Bearer token",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "ctx": {
                        "byte_position": 4,
                        "column": 5,
                        "error": "JSON is malformed: invalid character (byte 4)",
                        "line": 1,
                    },
                    "input": "not valid json {{{",
                    "loc": ["body", 1, 5],
                    "msg": "Invalid JSON at line 1, column 5: JSON is malformed: invalid character (byte 4)\n  not valid json {{{\n      ^",
                    "type": "json_invalid",
                }
            ]
        }

    def test_search_invalid_operator_returns_422(
        self,
        mock_opensearch_client: MagicMock,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={
                "query": "test",
                "where": {
                    "field": "tags",
                    "op": "invalid_operator",
                    "value": ["tag1"],
                },
                "limit": 10,
            },
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body"],
                    "msg": "'invalid_operator' is not a valid Operator",
                    "type": "validation_error",
                }
            ]
        }

    def test_search_invalid_sort_field_returns_422(
        self,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={
                "query": "test",
                "sort": [{"field": "nonexistent_field", "direction": "desc"}],
                "limit": 10,
            },
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "sort0.field"],
                    "msg": "Invalid enum value 'nonexistent_field'",
                    "type": "validation_error",
                }
            ]
        }

    def test_search_invalid_sort_direction_returns_422(
        self,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={
                "query": "test",
                "sort": [{"field": "created_at", "direction": "invalid"}],
                "limit": 10,
            },
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "sort0.direction"],
                    "msg": "Invalid enum value 'invalid'",
                    "type": "validation_error",
                }
            ]
        }
