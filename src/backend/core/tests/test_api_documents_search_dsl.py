"""Tests for search documents API with structured query DSL."""

import pytest
import responses
from rest_framework.test import APIClient

from core import factories
from core.utils import prepare_index

from .utils import build_authorization_bearer, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


def test_api_search_dsl_anonymous():
    """Anonymous requests should not be allowed to search."""
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"query": "test"},
        format="json",
    )

    assert response.status_code == 401


@responses.activate
def test_api_search_dsl_basic_query(settings):
    """Authenticated users should be able to search with basic query."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        3,
        reach="public",
        is_active=True,
        users=["user_sub"],
    )
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"query": ""},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 3


@responses.activate
def test_api_search_dsl_with_where_reach(settings):
    """Authenticated users should be able to filter by reach."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    public_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=True,
        users=["user_sub"],
    )
    restricted_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="restricted",
        is_active=True,
        users=["user_sub"],
    )
    prepare_index(service.index_name, public_docs + restricted_docs)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "where": {"field": "reach", "op": "eq", "value": "public"},
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    for result in results:
        assert result["_source"]["reach"] == "public"


@responses.activate
def test_api_search_dsl_with_where_tags(settings):
    """Authenticated users should be able to filter by tags."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    tagged_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=True,
        users=["user_sub"],
        tags=["finance", "report"],
    )
    untagged_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=True,
        users=["user_sub"],
        tags=["other"],
    )
    prepare_index(service.index_name, tagged_docs + untagged_docs)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "where": {"field": "tags", "op": "in", "value": ["finance"]},
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    for result in results:
        assert "finance" in result["_source"]["tags"]


@responses.activate
def test_api_search_dsl_with_sort(settings):
    """Authenticated users should be able to sort results."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            reach="public",
            is_active=True,
            users=["user_sub"],
            size=100,
        ),
        factories.DocumentSchemaFactory.build(
            reach="public",
            is_active=True,
            users=["user_sub"],
            size=300,
        ),
        factories.DocumentSchemaFactory.build(
            reach="public",
            is_active=True,
            users=["user_sub"],
            size=200,
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "sort": [{"field": "size", "direction": "asc"}],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 3
    sizes = [r["_source"]["size"] for r in results]
    assert sizes == sorted(sizes)


@responses.activate
def test_api_search_dsl_with_limit(settings):
    """Authenticated users should be able to limit results."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        10,
        reach="public",
        is_active=True,
        users=["user_sub"],
    )
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "limit": 5,
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 5


@responses.activate
def test_api_search_dsl_empty_where(settings):
    """Search without where clause should apply SystemScope filters only."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    active_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=True,
        users=["user_sub"],
    )
    inactive_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=False,
        users=["user_sub"],
    )
    prepare_index(service.index_name, active_docs + inactive_docs)

    active_ids = {doc["id"] for doc in active_docs}

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"query": ""},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    result_ids = {hit["_id"] for hit in results}
    assert len(results) == 2
    assert result_ids == active_ids


@responses.activate
def test_api_search_dsl_with_and_clause(settings):
    """Authenticated users should be able to use AND clause for complex filters."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    matching_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=True,
        users=["user_sub"],
        tags=["finance"],
    )
    public_only_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=True,
        users=["user_sub"],
        tags=["other"],
    )
    tagged_only_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="restricted",
        is_active=True,
        users=["user_sub"],
        tags=["finance"],
    )
    prepare_index(
        service.index_name, matching_docs + public_only_docs + tagged_only_docs
    )

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "where": {
                "and": [
                    {"field": "reach", "op": "eq", "value": "public"},
                    {"field": "tags", "op": "in", "value": ["finance"]},
                ]
            },
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    for result in results:
        assert result["_source"]["reach"] == "public"
        assert "finance" in result["_source"]["tags"]


@responses.activate
def test_api_search_dsl_blocked_field_users(settings):
    """Filtering by 'users' field should be blocked with 400 response."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "where": {"field": "users", "op": "in", "value": ["malicious_user"]},
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert "literal_error" in str(response.json())


@responses.activate
def test_api_search_dsl_blocked_field_groups(settings):
    """Filtering by 'groups' field should be blocked with 400 response."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "where": {"field": "groups", "op": "in", "value": ["admin_group"]},
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert "literal_error" in str(response.json())


@responses.activate
def test_api_search_dsl_blocked_field_is_active(settings):
    """Filtering by 'is_active' field should be blocked with 400 response."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "where": {"field": "is_active", "op": "eq", "value": False},
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert "literal_error" in str(response.json())


@responses.activate
def test_api_search_dsl_blocked_field_nested(settings):
    """Blocked field nested inside AND clause should be detected and rejected."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "query": "",
            "where": {
                "and": [
                    {"field": "reach", "op": "eq", "value": "public"},
                    {"field": "users", "op": "in", "value": ["hidden_user"]},
                ]
            },
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert "literal_error" in str(response.json())


@responses.activate
def test_api_search_dsl_restricted_doc_invisible_without_access(settings):
    """Restricted docs should not be visible to users without access."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    accessible_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="public",
        is_active=True,
        users=["user_sub"],
    )
    inaccessible_restricted_docs = factories.DocumentSchemaFactory.build_batch(
        2,
        reach="restricted",
        is_active=True,
        users=["other_user"],
    )
    prepare_index(service.index_name, accessible_docs + inaccessible_restricted_docs)

    accessible_ids = {doc["id"] for doc in accessible_docs}
    inaccessible_ids = {doc["id"] for doc in inaccessible_restricted_docs}

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"query": ""},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    result_ids = {hit["_id"] for hit in results}

    assert result_ids == accessible_ids
    assert result_ids.isdisjoint(inaccessible_ids)
