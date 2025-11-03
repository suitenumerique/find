"""
Test suite for access control when searching documents over the API.

Don't use pytest parametrized tests because batch generation and indexing
of documents is slow and better done only once.
"""

import pytest
import responses
from rest_framework.test import APIClient

from core import enums, factories

from core.services.opensearch import opensearch_client

from .mock import albert_embedding_response
from .utils import (
    build_authorization_bearer,
    delete_test_indices,
    prepare_index,
    setup_oicd_resource_server,
)

pytestmark = pytest.mark.django_db


@responses.activate
def test_api_documents_search_access_control_anonymous(settings):
    """Anonymous users should not be allowed to search documents even public."""
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory(name="test-service")
    documents = []
    for reach in enums.ReachEnum:
        documents.extend(factories.DocumentSchemaFactory.build_batch(3, reach=reach))
    prepare_index(service.name, documents)

    response = APIClient().post("/api/v1.0/documents/search/?q=*")

    assert response.status_code == 401


@responses.activate
def test_api_documents_search_access_control(settings):
    """
    Authenticated users should only see documents:
    - for which they are listed in the "users" field
    - that have a reach set to "authenticated" or "public"
    - only configured services providers are allowed (e.g docs)
    (groups is not yet implemnted)
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    documents_reach = factories.DocumentSchemaFactory.build_batch(6)
    documents_open = [
        doc for doc in documents_reach if doc["reach"] in ["authenticated", "public"]
    ]
    documents_user = factories.DocumentSchemaFactory.build_batch(
        6, users=["user_sub", "user_sub2"]
    )
    expected_ids = [doc["id"] for doc in documents_open + documents_user]

    prepare_index(service.name, documents_user + documents_reach)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": [d["id"] for d in documents_open]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["_id"] for d in response.json()]) == sorted(expected_ids)


@responses.activate
@pytest.mark.parametrize(
    "doc_ids,visited,expected",
    [
        (["a", "b"], [], []),
        (["a", "b"], "", []),
        (["a", "b"], None, []),
        (["a", "b"], ["other"], []),
        ([], ["a"], []),
        (["a", "b"], ["a"], ["a"]),
        (["a", "b"], ["a", "b", "c"], ["a", "b"]),
        (["a", "b"], "a,b,c", ["a", "b"]),
    ],
)
def test_api_documents_search_access__only_visited_public(
    doc_ids, visited, expected, settings
):
    """
    Authenticated users should only see documents with reach="public"
    that are in "visited" list.
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="docs")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service", client_id="docs")

    docs = [
        factories.DocumentSchemaFactory(
            reach=[enums.ReachEnum.PUBLIC, enums.ReachEnum.AUTHENTICATED], id=doc_id
        )
        for doc_id in doc_ids
    ]

    prepare_index(service.name, docs)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": visited},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200, response.json()
    assert sorted([d["_id"] for d in response.json()]) == sorted(expected)


@responses.activate
def test_api_documents_search_access__any_owner_public(settings):
    """
    Authenticated users should only see documents with reach="public"
    that are in "visited" list.
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="docs")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service", client_id="docs")

    docs = factories.DocumentSchemaFactory.build_batch(
        6,
        reach=enums.ReachEnum.PUBLIC,
        users=["user_sub"],
    )

    other_docs = factories.DocumentSchemaFactory.build_batch(
        6,
        reach=enums.ReachEnum.PUBLIC,
        users=["other_sub"],
    )

    prepare_index(service.name, docs + other_docs)

    expected = [d["id"] for d in docs]

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200, response.json()
    assert sorted([d["_id"] for d in response.json()]) == sorted(expected)


@responses.activate
def test_api_documents_search_access__services(settings):
    """
    Authenticated users should only see documents of audience
    service providers (e.g docs)
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="a-client")
    token = build_authorization_bearer()

    service_a = factories.ServiceFactory(name="test-index-a", client_id="a-client")
    service_b = factories.ServiceFactory(name="test-index-b", client_id="b-client")

    service_a_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_b_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )

    expected_ids = [doc["id"] for doc in service_a_docs]

    prepare_index(service_a.name, service_a_docs)
    prepare_index(service_b.name, service_b_docs, cleanup=False)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["_id"] for d in response.json()]) == sorted(expected_ids)


@responses.activate
def test_api_documents_search_access__missing_index(settings):
    """
    When the service has no opensearch index, returns an empty list.
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="a-client")
    token = build_authorization_bearer()
    factories.ServiceFactory(name="test-index-a", client_id="a-client")

    delete_test_indices()
    opensearch_client.cache_clear()

    # a-client has no index. ignore it.
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert response.json() == []


@responses.activate
def test_api_documents_search_access__related_services(settings):
    """
    Authenticated users should only see documents of audience
    service providers and its related services (e.g drive + docs)
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="c-client")
    token = build_authorization_bearer()

    service_a = factories.ServiceFactory(name="test-index-a", client_id="a-client")
    service_b = factories.ServiceFactory(name="test-index-b", client_id="b-client")
    service_c = factories.ServiceFactory(name="test-index-c", client_id="c-client")
    service_c.services.set([service_a])
    service_c.save()

    service_a_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_b_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_c_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )

    expected_ids = [doc["id"] for doc in service_a_docs + service_c_docs]

    prepare_index(service_a.name, service_a_docs)
    prepare_index(service_b.name, service_b_docs, cleanup=False)
    prepare_index(service_c.name, service_c_docs, cleanup=False)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["_id"] for d in response.json()]) == sorted(expected_ids)


@responses.activate
def test_api_documents_search_access__related_missing_index(settings):
    """
    When the service has no opensearch index, returns the related services data.
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="a-client")
    token = build_authorization_bearer()

    service_a = factories.ServiceFactory(name="test-index-a", client_id="a-client")
    service_b = factories.ServiceFactory(name="test-index-b", client_id="b-client")
    service_c = factories.ServiceFactory(name="test-index-c", client_id="c-client")
    service_c.services.set([service_a])
    service_c.save()

    service_b_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_c_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )

    expected_ids = [doc["id"] for doc in service_c_docs]

    prepare_index(service_b.name, service_b_docs)
    prepare_index(service_c.name, service_c_docs, cleanup=False)

    # a-client has no index. ignore it.
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["_id"] for d in response.json()]) == sorted(expected_ids)


@responses.activate
def test_api_documents_search_access__request_services(settings):
    """
    Authenticated users should only see documents of audience
    from requested services : 'services' parameter.
    Raise 400 error if not all requested services are authorized.
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="c-client")
    token = build_authorization_bearer()

    service_a = factories.ServiceFactory(name="test-index-a", client_id="a-client")
    service_b = factories.ServiceFactory(name="test-index-b", client_id="b-client")
    service_c = factories.ServiceFactory(name="test-index-c", client_id="c-client")

    service_a_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_b_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_c_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )

    expected_ids = [doc["id"] for doc in service_c_docs]

    prepare_index(service_a.name, service_a_docs)
    prepare_index(service_b.name, service_b_docs, cleanup=False)
    prepare_index(service_c.name, service_c_docs, cleanup=False)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "services": ["test-index-c"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["_id"] for d in response.json()]) == sorted(expected_ids)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "services": ["test-index-c", "test-index-b"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Some requested services are not available"}


@responses.activate
def test_api_documents_search_access__request_inactive_services(settings):
    """
    Authenticated users should only see documents of audience
    from requested services : 'services' parameter.
    Raise 400 error if not all requested services are active.
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="client")
    token = build_authorization_bearer()

    factories.ServiceFactory(name="test-index", client_id="client", is_active=False)
    factories.ServiceFactory(name="test-index-b", client_id="b-client")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "services": ["test-index"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Service is not available"}

    # Event without explicit argument, the client service from the request is not active
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Service is not available"}


@responses.activate
def test_api_documents_search_access__authenticated(settings):
    """
    Authenticated users should only see documents
    - for which they are listed in the "users" field
    - that have a reach set to "authenticated" or "public" AND in visited list
    - only configured services providers are allowed (e.g docs)
    (groups is not yet implemnted)
    """
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="docs")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service", client_id="docs")

    documents_open = factories.DocumentSchemaFactory.build_batch(
        2, reach=enums.ReachEnum.PUBLIC
    ) + factories.DocumentSchemaFactory.build_batch(
        2, reach=enums.ReachEnum.AUTHENTICATED
    )

    documents_restricted = factories.DocumentSchemaFactory.build_batch(
        2, reach=enums.ReachEnum.RESTRICTED
    )

    documents_user = factories.DocumentSchemaFactory.build_batch(
        6, users=["user_sub", "user_sub2"]
    )
    documents = documents_user + documents_open + documents_restricted

    prepare_index(service.name, documents_user + documents_open + documents_restricted)

    # Only owned documents (reach is ignored)
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200

    assert sorted([d["_id"] for d in response.json()]) == sorted(
        [doc["id"] for doc in documents_user]
    )

    # Owned documents and visited public/authenticated ones.
    # Restricted ones from another owner are filtered (even if given as visited ones)
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": [d["id"] for d in documents]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200

    assert sorted([d["_id"] for d in response.json()]) == sorted(
        [doc["id"] for doc in documents_user + documents_open]
    )
