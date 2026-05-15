from unittest.mock import MagicMock

from django.conf import LazySettings

import pytest
from django_bolt.testing import TestClient

from core import enums
from core.authentication import ResourceUser

pytestmark = pytest.mark.django_db


class TestSearchDocumentsHandler:
    def test_search_simple_query_returns_200(
        self,
        settings: LazySettings,
        mock_opensearch_client: MagicMock,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        mock_opensearch_client.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_id": "doc1",
                        "_source": {
                            "title": "Test Document",
                            "content": "content1",
                            "size": 100,
                            "depth": 0,
                            "path": "/test",
                            "numchild": 0,
                            "created_at": "2024-01-01T00:00:00Z",
                            "updated_at": "2024-01-02T00:00:00Z",
                        },
                    },
                    {
                        "_id": "doc2",
                        "_source": {
                            "title": "Another Document",
                            "content": "content2",
                            "size": 200,
                            "depth": 1,
                            "path": "/test/sub",
                            "numchild": 0,
                            "created_at": "2024-01-01T00:00:00Z",
                            "updated_at": "2024-01-02T00:00:00Z",
                        },
                    },
                ],
            }
        }

        response = bolt_client.post(
            "/api/v1.0/documents/search",
            json={"query": "test", "limit": 10},
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "data": [
                {
                    "id": "doc1",
                    "title": "Test Document",
                    "content": "content1",
                    "size": 100,
                    "depth": 0,
                    "path": "/test",
                    "numchild": 0,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-02T00:00:00Z",
                    "reach": None,
                    "tags": [],
                    "number_of_users": None,
                    "number_of_groups": None,
                },
                {
                    "id": "doc2",
                    "title": "Another Document",
                    "content": "content2",
                    "size": 200,
                    "depth": 1,
                    "path": "/test/sub",
                    "numchild": 0,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-02T00:00:00Z",
                    "reach": None,
                    "tags": [],
                    "number_of_users": None,
                    "number_of_groups": None,
                },
            ],
            "total": 2,
            "limit": 10,
        }
        mock_opensearch_client.search.assert_called_once()
        assert mock_opensearch_client.search.call_args.kwargs == {
            "index": settings.OPENSEARCH_INDEX,
            "body": {
                "_source": enums.SOURCE_FIELDS,
                "script_fields": {
                    "number_of_users": {"script": {"source": "doc['users'].size()"}},
                    "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
                },
                "sort": [{"_score": {"order": "desc"}}],
                "size": 10,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "bool": {
                                    "should": [
                                        {
                                            "multi_match": {
                                                "query": "test",
                                                "fields": ["title.*.text^3", "content.*"],
                                            }
                                        },
                                        {
                                            "multi_match": {
                                                "query": "test",
                                                "fields": [
                                                    "title.*.text.trigrams^3",
                                                    "content.*.trigrams",
                                                ],
                                                "boost": settings.TRIGRAMS_BOOST,
                                                "minimum_should_match": settings.TRIGRAMS_MINIMUM_SHOULD_MATCH,
                                            }
                                        },
                                    ],
                                    "minimum_should_match": 1,
                                }
                            }
                        ],
                        "filter": [
                            {
                                "bool": {
                                    "must": [
                                        {"term": {"is_active": True}},
                                        {"term": {"service": mock_oidc_user.token_audience}},
                                        {
                                            "bool": {
                                                "should": [
                                                    {
                                                        "bool": {
                                                            "must_not": [
                                                                {"term": {"reach": "restricted"}}
                                                            ]
                                                        }
                                                    },
                                                    {"terms": {"users": [mock_oidc_user.sub]}},
                                                ],
                                                "minimum_should_match": 1,
                                            }
                                        },
                                    ]
                                }
                            }
                        ],
                    }
                },
            },
            "params": {"ignore_unavailable": "true"},
        }

    def test_search_with_where_clause_returns_200(
        self,
        settings: LazySettings,
        mock_opensearch_client: MagicMock,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        mock_opensearch_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

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
        mock_opensearch_client.search.assert_called_once()
        assert mock_opensearch_client.search.call_args.kwargs == {
            "index": settings.OPENSEARCH_INDEX,
            "body": {
                "_source": enums.SOURCE_FIELDS,
                "script_fields": {
                    "number_of_users": {"script": {"source": "doc['users'].size()"}},
                    "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
                },
                "sort": [{"_score": {"order": "desc"}}],
                "size": 10,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "bool": {
                                    "should": [
                                        {
                                            "multi_match": {
                                                "query": "test",
                                                "fields": ["title.*.text^3", "content.*"],
                                            }
                                        },
                                        {
                                            "multi_match": {
                                                "query": "test",
                                                "fields": [
                                                    "title.*.text.trigrams^3",
                                                    "content.*.trigrams",
                                                ],
                                                "boost": settings.TRIGRAMS_BOOST,
                                                "minimum_should_match": settings.TRIGRAMS_MINIMUM_SHOULD_MATCH,
                                            }
                                        },
                                    ],
                                    "minimum_should_match": 1,
                                }
                            }
                        ],
                        "filter": [
                            {
                                "bool": {
                                    "must": [
                                        {
                                            "bool": {
                                                "must": [
                                                    {"terms": {"tags": ["tag1", "tag2"]}}
                                                ]
                                            }
                                        },
                                        {
                                            "bool": {
                                                "must": [
                                                    {"term": {"is_active": True}},
                                                    {"term": {"service": mock_oidc_user.token_audience}},
                                                    {
                                                        "bool": {
                                                            "should": [
                                                                {
                                                                    "bool": {
                                                                        "must_not": [
                                                                            {"term": {"reach": "restricted"}}
                                                                        ]
                                                                    }
                                                                },
                                                                {"terms": {"users": [mock_oidc_user.sub]}},
                                                            ],
                                                            "minimum_should_match": 1,
                                                        }
                                                    },
                                                ]
                                            }
                                        },
                                    ]
                                }
                            }
                        ],
                    }
                },
            },
            "params": {"ignore_unavailable": "true"},
        }

    def test_search_with_sort_and_limit_returns_200(
        self,
        settings: LazySettings,
        mock_opensearch_client: MagicMock,
        mock_oidc_user: ResourceUser,
        bolt_client: TestClient,
    ) -> None:
        mock_opensearch_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

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
        mock_opensearch_client.search.assert_called_once()
        assert mock_opensearch_client.search.call_args.kwargs == {
            "index": settings.OPENSEARCH_INDEX,
            "body": {
                "_source": enums.SOURCE_FIELDS,
                "script_fields": {
                    "number_of_users": {"script": {"source": "doc['users'].size()"}},
                    "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
                },
                "sort": [{"created_at": {"order": "desc"}}],
                "size": 5,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "bool": {
                                    "should": [
                                        {
                                            "multi_match": {
                                                "query": "test",
                                                "fields": ["title.*.text^3", "content.*"],
                                            }
                                        },
                                        {
                                            "multi_match": {
                                                "query": "test",
                                                "fields": [
                                                    "title.*.text.trigrams^3",
                                                    "content.*.trigrams",
                                                ],
                                                "boost": settings.TRIGRAMS_BOOST,
                                                "minimum_should_match": settings.TRIGRAMS_MINIMUM_SHOULD_MATCH,
                                            }
                                        },
                                    ],
                                    "minimum_should_match": 1,
                                }
                            }
                        ],
                        "filter": [
                            {
                                "bool": {
                                    "must": [
                                        {"term": {"is_active": True}},
                                        {"term": {"service": mock_oidc_user.token_audience}},
                                        {
                                            "bool": {
                                                "should": [
                                                    {
                                                        "bool": {
                                                            "must_not": [
                                                                {"term": {"reach": "restricted"}}
                                                            ]
                                                        }
                                                    },
                                                    {"terms": {"users": [mock_oidc_user.sub]}},
                                                ],
                                                "minimum_should_match": 1,
                                            }
                                        },
                                    ]
                                }
                            }
                        ],
                    }
                },
            },
            "params": {"ignore_unavailable": "true"},
        }

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
                    "loc": ["body", "sort.0.field"],
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
                    "loc": ["body", "sort.0.direction"],
                    "msg": "Invalid enum value 'invalid'",
                    "type": "validation_error",
                }
            ]
        }
