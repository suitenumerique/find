"""
Test suite for searching documents in OpenSearch over the API.

Don't use pytest parametrized tests because batch generation and indexing
of documents is slow and better done only once.
"""

import operator
import random

import pytest
import responses
from rest_framework.test import APIClient

from core import enums, factories
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client

from .mock import albert_embedding_response
from .utils import (
    build_authorization_bearer,
    bulk_create_documents,
    enable_hybrid_search,
    prepare_index,
    setup_oicd_resource_server,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def before_each():
    """Clear cached functions before each test to avoid side effects"""
    clear_caches()
    yield
    clear_caches()


def clear_caches():
    """Clear cached functions before each test to avoid side effects"""
    opensearch_client.cache_clear()
    check_hybrid_search_enabled.cache_clear()


@responses.activate
def test_api_documents_search_auth_invalid_parameters(settings):
    """Invalid service parameters should result in a 401 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    settings.OIDC_RS_CLIENT_ID = None
    settings.OIDC_RS_CLIENT_SECRET = None

    service = factories.ServiceFactory()
    prepare_index(service.index_name, [])

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox"},
        format="json",
        HTTP_AUTHORIZATION="Bearer unknown",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Resource Server is improperly configured"}


@responses.activate
def test_api_documents_search_opensearch_env_variables_not_set(settings):
    """
    Missing environment variables for OpenSearch client should
    result in a 500 internal server error
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    del settings.OPENSEARCH_HOST  # Remove required settings
    del settings.OPENSEARCH_PASSWORD

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        "Missing required OpenSearch environment variables: OPENSEARCH_HOST, OPENSEARCH_PASSWORD"
    ]


@responses.activate
def test_api_documents_search_query_unknown_user(settings):
    """Searching a document without an existing user should result in a 401 error"""
    setup_oicd_resource_server(
        responses,
        settings,
        sub="unknown",
        introspect=lambda request, user_info: (404, {}, ""),
    )

    token = build_authorization_bearer()

    service = factories.ServiceFactory()
    prepare_index(service.index_name, [])

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Login failed"}


@responses.activate
def test_api_documents_search_services_invalid_parameters(settings):
    """Invalid services parameter should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    factories.ServiceFactory()

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        # services should be a list
        {"q": "a quick fox", "services": {}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "loc": ["services"],
            "msg": "Value error, ",
            "type": "value_error",
        }
    ]


@responses.activate
def test_api_documents_search_reached_docs_invalid_parameters(settings):
    """Invalid visited parameters should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    factories.ServiceFactory()

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        # visited should be a list
        {"q": "a quick fox", "visited": {}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "loc": ["visited"],
            "msg": "Value error, ",
            "type": "value_error",
        }
    ]


@responses.activate
def test_api_documents_search_match_all(settings):
    """Searching a document with q='*' should match all docs"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    nb_documents = 12
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        nb_documents, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*", "visited": [doc["id"] for doc in documents]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == nb_documents

    assert [r["_id"] for r in response.json()] == [str(doc["id"]) for doc in documents]


@responses.activate
def test_api_documents_full_text_search_query_title(settings):
    """Searching a document by its title should work as expected"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    documents = bulk_create_documents(
        [
            {"title": "The quick brown fox", "content": "the wolf"},
            {"title": "The blue fox", "content": "the wolf"},
            {"title": "The brown goat", "content": "the wolf"},
        ]
    )

    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": [doc["id"] for doc in documents]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 2

    fox_response = response.json()[0]
    fox_document = documents[0]
    assert list(fox_response.keys()) == ["_index", "_id", "_score", "_source", "fields"]
    assert fox_response["_id"] == str(documents[0]["id"])
    assert fox_response["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": fox_document["path"],
        "size": fox_document["size"],
        "created_at": fox_document["created_at"].isoformat(),
        "updated_at": fox_document["updated_at"].isoformat(),
        "reach": fox_document["reach"],
        "title": fox_document["title"],
    }
    assert fox_response["fields"] == {"number_of_users": [1], "number_of_groups": [3]}

    other_fox_response = response.json()[1]
    other_fox_document = documents[1]
    assert list(other_fox_response.keys()) == [
        "_index",
        "_id",
        "_score",
        "_source",
        "fields",
    ]
    assert other_fox_response["_id"] == str(other_fox_document["id"])
    assert other_fox_response["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": other_fox_document["path"],
        "size": other_fox_document["size"],
        "created_at": other_fox_document["created_at"].isoformat(),
        "updated_at": other_fox_document["updated_at"].isoformat(),
        "reach": other_fox_document["reach"],
        "title": other_fox_document["title"],
    }
    assert other_fox_response["fields"] == {
        "number_of_users": [1],
        "number_of_groups": [3],
    }


@responses.activate
def test_api_documents_full_text_search(settings):
    """Searching a document by its content should work as expected"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory()
    documents = bulk_create_documents(
        [
            {"title": "The quick brown fox", "content": "the wolf"},
            {"title": "The blue fox", "content": "the wolf"},
            {"title": "The brown goat", "content": "the wolf"},
        ]
    )
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": [doc["id"] for doc in documents]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 2

    fox_response = response.json()[0]
    fox_document = documents[0]
    assert list(fox_response.keys()) == ["_index", "_id", "_score", "_source", "fields"]
    assert fox_response["_id"] == str(fox_document["id"])
    assert fox_response["_score"] > 0
    assert fox_response["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": fox_document["path"],
        "size": fox_document["size"],
        "created_at": fox_document["created_at"].isoformat(),
        "updated_at": fox_document["updated_at"].isoformat(),
        "reach": fox_document["reach"],
        "title": fox_document["title"],
    }
    assert fox_response["fields"] == {"number_of_users": [1], "number_of_groups": [3]}

    other_fox_response = response.json()[1]
    other_fox_document = documents[1]
    assert list(other_fox_response.keys()) == [
        "_index",
        "_id",
        "_score",
        "_source",
        "fields",
    ]
    assert other_fox_response["_id"] == str(other_fox_document["id"])
    assert other_fox_response["_score"] > 0
    assert other_fox_response["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": other_fox_document["path"],
        "size": other_fox_document["size"],
        "created_at": other_fox_document["created_at"].isoformat(),
        "updated_at": other_fox_document["updated_at"].isoformat(),
        "reach": other_fox_document["reach"],
        "title": other_fox_document["title"],
    }
    assert other_fox_response["fields"] == {
        "number_of_users": [1],
        "number_of_groups": [3],
    }


@responses.activate
def test_api_documents_hybrid_search(settings):
    """Searching a document by its content should work as expected"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    # hybrid search is enabled by default
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )  # mock embedding API

    service = factories.ServiceFactory()
    documents = bulk_create_documents(
        [
            {"title": "The quick brown fox", "content": "the wolf"},
            {"title": "The blue fox", "content": "the wolf"},
            {"title": "The brown goat", "content": "the wolf"},
        ]
    )
    prepare_index(service.index_name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": [doc["id"] for doc in documents]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert (
        len(response.json()) == 3
    )  # semantic search always returns a response of size nb_results

    fox_response = response.json()[0]
    fox_document = documents[0]
    assert list(fox_response.keys()) == ["_index", "_id", "_score", "_source", "fields"]
    assert fox_response["_id"] == str(fox_document["id"])
    assert fox_response["_score"] > 0
    assert fox_response["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": fox_document["path"],
        "size": fox_document["size"],
        "created_at": fox_document["created_at"].isoformat(),
        "updated_at": fox_document["updated_at"].isoformat(),
        "reach": fox_document["reach"],
        "title": fox_document["title"],
    }
    assert fox_response["fields"] == {"number_of_users": [1], "number_of_groups": [3]}

    other_fox_response = response.json()[1]
    other_fox_document = documents[1]
    assert list(other_fox_response.keys()) == [
        "_index",
        "_id",
        "_score",
        "_source",
        "fields",
    ]
    assert other_fox_response["_id"] == str(other_fox_document["id"])
    assert other_fox_response["_score"] > 0
    assert other_fox_response["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": other_fox_document["path"],
        "size": other_fox_document["size"],
        "created_at": other_fox_document["created_at"].isoformat(),
        "updated_at": other_fox_document["updated_at"].isoformat(),
        "reach": other_fox_document["reach"],
        "title": other_fox_document["title"],
    }
    assert other_fox_response["fields"] == {
        "number_of_users": [1],
        "number_of_groups": [3],
    }

    no_fox_response = response.json()[2]
    no_fox_document = documents[2]
    assert list(no_fox_response.keys()) == [
        "_index",
        "_id",
        "_score",
        "_source",
        "fields",
    ]
    assert no_fox_response["_id"] == str(no_fox_document["id"])
    assert no_fox_response["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": no_fox_document["path"],
        "size": no_fox_document["size"],
        "created_at": no_fox_document["created_at"].isoformat(),
        "updated_at": no_fox_document["updated_at"].isoformat(),
        "reach": no_fox_document["reach"],
        "title": no_fox_document["title"],
    }
    assert no_fox_response["fields"] == {
        "number_of_users": [1],
        "number_of_groups": [3],
    }


@responses.activate
def test_api_documents_search_ordering_by_fields(settings):
    """It should be possible to order by several fields"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    parameters = [
        (enums.TITLE, "asc"),
        (enums.TITLE, "desc"),
        (enums.CREATED_AT, "asc"),
        (enums.CREATED_AT, "desc"),
        (enums.UPDATED_AT, "asc"),
        (enums.UPDATED_AT, "desc"),
        (enums.SIZE, "asc"),
        (enums.SIZE, "desc"),
        (enums.REACH, "asc"),
        (enums.REACH, "desc"),
    ]

    for field, direction in parameters:
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "q": "*",
                "order_by": field,
                "order_direction": direction,
                "visited": [doc["id"] for doc in documents],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4

        # Check that results are sorted by the field as expected
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(data) - 1):
            assert compare(data[i]["_source"][field], data[i + 1]["_source"][field])


@responses.activate
def test_api_documents_search_ordering_by_relevance(settings):
    """It should be possible to order by relevance (score)"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    for direction in ["asc", "desc"]:
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "q": "*",
                "order_by": "relevance",
                "order_direction": direction,
                "visited": [doc["id"] for doc in documents],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4

        # Check that results are sorted by score as expected
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(data) - 1):
            assert compare(data[i]["_score"], data[i + 1]["_score"])


@responses.activate
def test_api_documents_search_ordering_by_unknown_field(settings):
    """Trying to sort by an unknown field should return a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    # Setup: Initialize the service and documents only once
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        2, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    # Define the parameters manually
    directions = ["asc", "desc"]

    # Perform the parameterized tests
    for direction in directions:
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "q": "*",
                "order_by": "unknown",
                "order_direction": direction,
                "visited": [doc["id"] for doc in documents],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 400
        assert response.json() == [
            {
                "loc": ["order_by"],
                "msg": (
                    "Input should be 'relevance', 'title', 'created_at', "
                    "'updated_at', 'size' or 'reach'"
                ),
                "type": "literal_error",
            }
        ]


@responses.activate
def test_api_documents_search_ordering_by_unknown_direction(settings):
    """Trying to sort with an unknown direction should return a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        2, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    for field in enums.ORDER_BY_OPTIONS:
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "q": "*",
                "order_by": field,
                "order_direction": "unknown",
                "visited": [doc["id"] for doc in documents],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 400
        assert response.json() == [
            {
                "loc": ["order_direction"],
                "msg": "Input should be 'asc' or 'desc'",
                "type": "literal_error",
            }
        ]


@responses.activate
def test_api_documents_search_filtering_by_reach(settings):
    """It should be possible to filter results by their reach"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    for reach in enums.ReachEnum:
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {
                "q": "*",
                "reach": reach.value,
                "visited": [doc["id"] for doc in documents],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 200
        data = response.json()

        for result in data:
            assert reach == result["_source"]["reach"]


@responses.activate
def test_api_documents_search_with_nb_results(settings):
    """nb_size should correctly return results of given size"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        9, reach=random.choice(["public", "authenticated"])
    )
    ids = [str(doc["id"]) for doc in documents]
    prepare_index(service.index_name, documents)

    nb_results = 3
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "nb_results": nb_results,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    data = response.json()
    assert [r["_id"] for r in data] == ids[0:nb_results]

    nb_results = 6
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "nb_results": nb_results,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    data = response.json()
    assert [r["_id"] for r in data] == ids[0:nb_results]

    nb_results = 10
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "nb_results": nb_results,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    data = response.json()
    # nb_results > total number of documents => returns all documents
    assert [r["_id"] for r in data] == ids[0:9]


@responses.activate
def test_api_documents_search_nb_results_invalid_parameters(settings):
    """Invalid nb_results parameters should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.index_name, documents)

    parameters = [
        (
            "invalid",
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
        ),
        (-1, "greater_than_equal", "Input should be greater than or equal to 1"),
        (0, "greater_than_equal", "Input should be greater than or equal to 1"),
        (350, "less_than_equal", "Input should be less than or equal to 300"),
    ]

    for nb_results, error_type, error_message in parameters:
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "nb_results": nb_results},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 400
        assert response.data[0]["msg"] == error_message
        assert response.data[0]["type"] == error_type


@responses.activate
def test_api_documents_search_nb_results_with_filtering(settings):
    """nb_results should work correctly when combined with filtering by reach"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    service = factories.ServiceFactory()
    public_documents = factories.DocumentSchemaFactory.build_batch(3, reach="public")
    public_ids = [str(doc["id"]) for doc in public_documents]
    private_documents = factories.DocumentSchemaFactory.build_batch(
        2, reach="authenticated"
    )
    prepare_index(service.index_name, public_documents + private_documents)

    nb_results = 3
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "reach": "public",
            "nb_results": nb_results,
            "visited": public_ids,
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    assert [r["_id"] for r in response.json()] == public_ids[0:nb_results]
