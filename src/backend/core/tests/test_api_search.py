"""Tests for searching documents via the API endpoint POST /api/v1.0/documents/search/"""

import pytest
import responses
from rest_framework.test import APIClient

from core import enums, factories
from core.utils import prepare_index

from .utils import build_authorization_bearer, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


def test_api_search_anonymous():
    """Anonymous requests should not be allowed to search documents."""
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "test", "services": [], "visited": []},
        format="json",
    )

    assert response.status_code == 401


@responses.activate
def test_api_search_basic(settings):
    """Authenticated users should be able to search documents they have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Alpha Document Title",
            content="This is searchable content for testing",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Beta Document Title",
            content="Another document with different content",
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["_id"] == documents[0]["id"]


@responses.activate
def test_api_search_returns_multiple_results(settings):
    """Search should return multiple matching documents."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Document One",
            content="Common keyword found here",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Document Two",
            content="Common keyword also here",
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "common keyword",
            "services": [service.name],
            "visited": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    result_ids = {r["_id"] for r in results}
    assert result_ids == {documents[0]["id"], documents[1]["id"]}


@responses.activate
def test_api_search_filter_by_tags(settings):
    """Search results should be filterable by tags."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Tagged Document",
            content="Common search term in all docs",
            tags=["important", "project-alpha"],
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Untagged Document",
            content="Common search term in all docs",
            tags=["other-tag"],
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Another Tagged Document",
            content="Common search term in all docs",
            tags=["important", "project-beta"],
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "common",
            "services": [service.name],
            "visited": [],
            "tags": ["important"],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    result_ids = {r["_id"] for r in results}
    assert documents[0]["id"] in result_ids
    assert documents[2]["id"] in result_ids
    assert documents[1]["id"] not in result_ids


@responses.activate
def test_api_search_sort_by_created_at_desc(settings):
    """Search results should be sortable by created_at field in descending order."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Old Document",
            content="Searchable content here",
            created_at="2020-01-01T00:00:00Z",
            updated_at="2020-01-02T00:00:00Z",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="New Document",
            content="Searchable content here",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Middle Document",
            content="Searchable content here",
            created_at="2022-01-01T00:00:00Z",
            updated_at="2022-01-02T00:00:00Z",
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [],
            "order_by": "created_at",
            "order_direction": "desc",
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 3
    result_ids = [r["_id"] for r in results]
    assert result_ids == [documents[1]["id"], documents[2]["id"], documents[0]["id"]]


@responses.activate
def test_api_search_sort_by_created_at_asc(settings):
    """Search results should be sortable by created_at in ascending order."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Old Document",
            content="Searchable content here",
            created_at="2020-01-01T00:00:00Z",
            updated_at="2020-01-02T00:00:00Z",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="New Document",
            content="Searchable content here",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [],
            "order_by": "created_at",
            "order_direction": "asc",
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    result_ids = [r["_id"] for r in results]
    assert result_ids == [documents[0]["id"], documents[1]["id"]]


@responses.activate
def test_api_search_access_control_restricted_user(settings):
    """Users should only see restricted documents they have access to via user list."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="My Document",
            content="Searchable test content",
        ),
        factories.DocumentSchemaFactory.build(
            users=["other_user"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Others Document",
            content="Searchable test content",
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["_id"] == documents[0]["id"]


@responses.activate
def test_api_search_access_control_public_requires_visited(settings):
    """Public documents require the document ID to be in the visited list."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    public_doc = factories.DocumentSchemaFactory.build(
        users=[],
        groups=[],
        reach=enums.ReachEnum.PUBLIC,
        title="Public Document",
        content="Searchable test content",
    )
    restricted_doc = factories.DocumentSchemaFactory.build(
        users=["other_user"],
        groups=[],
        reach=enums.ReachEnum.RESTRICTED,
        title="Restricted to Other",
        content="Searchable test content",
    )
    prepare_index(service.index_name, [public_doc, restricted_doc])

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 0

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [str(public_doc["id"])],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["_id"] == public_doc["id"]


@responses.activate
def test_api_search_access_control_authenticated_requires_visited(settings):
    """Authenticated documents also require the document ID to be in the visited list."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    auth_doc = factories.DocumentSchemaFactory.build(
        users=[],
        groups=[],
        reach=enums.ReachEnum.AUTHENTICATED,
        title="Authenticated Document",
        content="Searchable test content",
    )
    prepare_index(service.index_name, [auth_doc])

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 0

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [str(auth_doc["id"])],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["_id"] == auth_doc["id"]


@responses.activate
def test_api_search_invalid_service(settings):
    """Requests with a wrong service name should return 400 Bad Request."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "test",
            "services": ["wrong-service"],
            "visited": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request."


@responses.activate
def test_api_search_nb_results_limit(settings):
    """Search should respect the nb_results parameter."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        10,
        users=["user_sub"],
        groups=[],
        reach=enums.ReachEnum.RESTRICTED,
        content="Searchable content here",
    )
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "searchable",
            "services": [service.name],
            "visited": [],
            "nb_results": 3,
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 3


@responses.activate
def test_api_search_match_all_with_asterisk(settings):
    """Search with '*' should return all accessible documents."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="First Document",
            content="Some content here",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Second Document",
            content="Other content here",
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "services": [service.name],
            "visited": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2


@responses.activate
def test_api_search_filter_by_multiple_tags(settings):
    """Search should return documents matching any of the provided tags (OR logic)."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Tag A Document",
            content="Common content",
            tags=["tag-a"],
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="Tag B Document",
            content="Common content",
            tags=["tag-b"],
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            groups=[],
            reach=enums.ReachEnum.RESTRICTED,
            title="No Tag Document",
            content="Common content",
            tags=["other"],
        ),
    ]
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "common",
            "services": [service.name],
            "visited": [],
            "tags": ["tag-a", "tag-b"],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    result_ids = {r["_id"] for r in results}
    assert documents[0]["id"] in result_ids
    assert documents[1]["id"] in result_ids
