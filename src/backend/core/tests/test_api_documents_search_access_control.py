"""
Test suite for access control when searching documents over the API.

Don't use pytest parametrized tests because batch generation and indexing
of documents is slow and better done only once.
"""

import random

from django.test import Client

import pytest
import responses

from core import enums, factories
from core.utils import prepare_index

from .utils import (
    build_authorization_bearer,
    setup_oicd_resource_server,
)

pytestmark = pytest.mark.django_db


def test_api_documents_search_access_control_anonymous():
    """Anonymous users should not be allowed to search documents even public."""
    service = factories.ServiceFactory()
    documents = []
    for reach in enums.ReachEnum:
        documents.extend(factories.DocumentSchemaFactory.build_batch(3, reach=reach))
    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/search/", {"q": "*"}, content_type="application/json"
    )

    assert response.status_code == 401


@responses.activate
def test_api_documents_search_access_control(settings):
    """
    Authenticated users should only see documents:
    - for which they are listed in the "users" field
    - that have a reach set to "authenticated" or "public"
    - only configured services providers are allowed (e.g docs)
    (groups is not yet implemented)
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory()
    documents_reach = factories.DocumentSchemaFactory.build_batch(6)
    documents_open = [
        doc for doc in documents_reach if doc["reach"] in ["authenticated", "public"]
    ]
    documents_user = factories.DocumentSchemaFactory.build_batch(
        6, users=["user_sub", "user_sub2"]
    )
    expected_ids = [doc["id"] for doc in documents_open + documents_user]

    prepare_index(service.index_name, documents_user + documents_reach)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": [d["id"] for d in documents_open]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(expected_ids)


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
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="docs")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(client_id="docs")

    docs = [
        factories.DocumentSchemaFactory(
            reach=random.choice(
                [enums.ReachEnum.PUBLIC, enums.ReachEnum.AUTHENTICATED]
            ),
            id=doc_id,
        )
        for doc_id in doc_ids
    ]

    prepare_index(service.index_name, docs)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": visited},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200, response.json()
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(expected)


@responses.activate
def test_api_documents_search_access__any_owner_public(settings):
    """
    Authenticated users should only see documents with reach="public"
    that are in "visited" list.
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="docs")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(client_id="docs")

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

    prepare_index(service.index_name, docs + other_docs)

    expected = [d["id"] for d in docs]

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": []},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200, response.json()
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(expected)


@responses.activate
def test_api_documents_search_access__services(settings):
    """
    Authenticated users should only see documents of audience
    service providers (e.g docs)
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="a-client")
    token = build_authorization_bearer()

    service_a = factories.ServiceFactory(client_id="a-client")
    service_b = factories.ServiceFactory(client_id="b-client")

    service_a_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_b_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )

    expected_ids = [doc["id"] for doc in service_a_docs]

    prepare_index(service_a.index_name, service_a_docs)
    prepare_index(service_b.index_name, service_b_docs)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(expected_ids)


@responses.activate
def test_api_documents_search_access__missing_index(settings):
    """
    When the service has no opensearch index, returns an empty list.
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="a-client")
    token = build_authorization_bearer()
    factories.ServiceFactory(name="test-index-a", client_id="a-client")

    # a-client has no index. ignore it.
    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert response.json() == {"results": []}


@responses.activate
def test_api_documents_search_access__related_services(settings):
    """
    Authenticated users should only see documents of audience
    service providers and its related services (e.g drive + docs)
    """
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

    prepare_index(service_a.index_name, service_a_docs)
    prepare_index(service_b.index_name, service_b_docs)
    prepare_index(service_c.index_name, service_c_docs)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(expected_ids)


@responses.activate
def test_api_documents_search_access__related_missing_index(settings):
    """
    When the service has no opensearch index, returns the related services data.
    """
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

    prepare_index(service_b.index_name, service_b_docs)
    prepare_index(service_c.index_name, service_c_docs)

    # a-client has no index. ignore it.
    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(expected_ids)


@responses.activate
def test_api_documents_search_access__request_services(settings):
    """
    Authenticated users should only see documents of audience
    from requested services : 'services' parameter.
    Raise 400 error if not all requested services are authorized.
    """
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

    prepare_index(service_a.index_name, service_a_docs)
    prepare_index(service_b.index_name, service_b_docs)
    prepare_index(service_c.index_name, service_c_docs)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "services": ["test-index-c"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(expected_ids)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "services": ["test-index-c", "test-index-b"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request."}


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

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "services": ["test-index"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request."}

    # Event without explicit argument, the client service from the request is not active
    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request."}


@responses.activate
def test_api_documents_search_access__authenticated(settings):
    """
    Authenticated users should only see documents
    - for which they are listed in the "users" field
    - that have a reach set to "authenticated" or "public" AND in visited list
    - only configured services providers are allowed (e.g docs)
    (groups is not yet implemented)
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="docs")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(client_id="docs")

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

    prepare_index(
        service.index_name, documents_user + documents_open + documents_restricted
    )

    # Only owned documents (reach is ignored)
    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200

    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(
        [doc["id"] for doc in documents_user]
    )

    # Owned documents and visited public/authenticated ones.
    # Restricted ones from another owner are filtered (even if given as visited ones)
    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": [d["id"] for d in documents]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200

    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(
        [doc["id"] for doc in documents_user + documents_open]
    )


@responses.activate
def test_api_documents_search_access__inactive_documents(settings):
    """
    Inactive documents should never be returned, even to their owner or when
    they are public and visited.
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory()

    active_documents = factories.DocumentSchemaFactory.build_batch(
        2, users=["user_sub"]
    )
    inactive_owned_documents = factories.DocumentSchemaFactory.build_batch(
        2, users=["user_sub"], is_active=False
    )
    inactive_public_documents = factories.DocumentSchemaFactory.build_batch(
        2, reach=enums.ReachEnum.PUBLIC, is_active=False
    )
    prepare_index(
        service.index_name,
        active_documents + inactive_owned_documents + inactive_public_documents,
    )

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": [d["id"] for d in inactive_public_documents]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(
        [doc["id"] for doc in active_documents]
    )


@responses.activate
def test_api_documents_search_access__full_text(settings):
    """Access control should also apply to full-text queries, not only to q='*'."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory()

    owned_document = factories.DocumentSchemaFactory.build(
        title="secret fox", users=["user_sub"]
    )
    visited_document = factories.DocumentSchemaFactory.build(
        title="public fox", reach=enums.ReachEnum.PUBLIC
    )
    other_documents = [
        factories.DocumentSchemaFactory.build(
            title="restricted fox", reach=enums.ReachEnum.RESTRICTED
        ),
        factories.DocumentSchemaFactory.build(
            title="authenticated fox", reach=enums.ReachEnum.AUTHENTICATED
        ),
    ]
    prepare_index(
        service.index_name, [owned_document, visited_document, *other_documents]
    )

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "fox", "visited": [visited_document["id"], other_documents[0]["id"]]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(
        [owned_document["id"], visited_document["id"]]
    )


@pytest.mark.xfail(
    strict=True, reason="#172: the services parameter is validated but not applied"
)
@responses.activate
def test_api_documents_search_access__request_related_service_only(settings):
    """
    Requesting a single allowed service through the 'services' parameter should
    restrict the search to that service.
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="c-client")
    token = build_authorization_bearer()

    service_a = factories.ServiceFactory(name="test-index-a", client_id="a-client")
    service_c = factories.ServiceFactory(name="test-index-c", client_id="c-client")
    service_c.services.set([service_a])

    service_a_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )
    service_c_docs = factories.DocumentSchemaFactory.build_batch(
        3, reach=enums.ReachEnum.AUTHENTICATED, users=["user_sub"]
    )

    prepare_index(service_a.index_name, service_a_docs)
    prepare_index(service_c.index_name, service_c_docs)

    response = Client().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "services": ["test-index-a"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert sorted([d["id"] for d in response.json()["results"]]) == sorted(
        [doc["id"] for doc in service_a_docs]
    )
