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

from .utils import build_authorization_bearer, prepare_index, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


@responses.activate
def test_api_documents_search_auth_invalid_parameters(settings):
    """Invalid service parameters should result in a 401 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    settings.OIDC_RS_CLIENT_ID = None
    settings.OIDC_RS_CLIENT_SECRET = None

    service = factories.ServiceFactory(name="test-service")
    prepare_index(service.name, [])

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox"},
        format="json",
        HTTP_AUTHORIZATION="Bearer unknown",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Resource Server is improperly configured"}


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

    service = factories.ServiceFactory(name="test-service")
    prepare_index(service.name, [])

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
    """Invalid pagination parameters should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    factories.ServiceFactory(name="test-service")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "services": {}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
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
    """Invalid pagination parameters should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    factories.ServiceFactory(name="test-service")

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": {}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
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
def test_api_documents_search_query_title(settings):
    """Searching a document by its title should work as expected"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build(
        title="The quick brown fox",
        content="the wolf",
        reach=random.choice(["public", "authenticated"]),
    )

    # Add other documents
    other_fox_document = factories.DocumentSchemaFactory.build(
        title="The blue fox",
        content="the wolf",
        reach=random.choice(["public", "authenticated"]),
    )
    no_fox_document = factories.DocumentSchemaFactory.build(
        title="The brown goat",
        content="the wolf",
        reach=random.choice(["public", "authenticated"]),
    )
    documents = [document, other_fox_document, no_fox_document]
    prepare_index(service.name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": [doc["id"] for doc in documents]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 2

    fox_data = response.json()[0]
    assert list(fox_data.keys()) == ["_index", "_id", "_score", "_source", "fields"]
    assert fox_data["_id"] == str(document["id"])
    assert fox_data["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": document["path"],
        "size": document["size"],
        "created_at": document["created_at"].isoformat(),
        "updated_at": document["updated_at"].isoformat(),
        "reach": document["reach"],
        "title": "The quick brown fox",
    }
    assert fox_data["fields"] == {"number_of_users": [3], "number_of_groups": [3]}

    other_fox_data = response.json()[1]
    assert list(other_fox_data.keys()) == [
        "_index",
        "_id",
        "_score",
        "_source",
        "fields",
    ]
    assert other_fox_data["_id"] == str(other_fox_document["id"])
    assert other_fox_data["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": other_fox_document["path"],
        "size": other_fox_document["size"],
        "created_at": other_fox_document["created_at"].isoformat(),
        "updated_at": other_fox_document["updated_at"].isoformat(),
        "reach": other_fox_document["reach"],
        "title": "The blue fox",
    }
    assert other_fox_data["fields"] == {"number_of_users": [3], "number_of_groups": [3]}


@responses.activate
def test_api_documents_search_query_content(settings):
    """Searching a document by its content should work as expected"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build(
        title="the wolf",
        content="The quick brown fox",
        reach=random.choice(["public", "authenticated"]),
    )

    # Add other documents
    other_fox_document = factories.DocumentSchemaFactory.build(
        title="the wolf",
        content="The blue fox",
        reach=random.choice(["public", "authenticated"]),
    )
    no_fox_document = factories.DocumentSchemaFactory.build(
        title="the wolf",
        content="The brown goat",
        reach=random.choice(["public", "authenticated"]),
    )

    documents = [document, other_fox_document, no_fox_document]
    prepare_index(service.name, documents)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "a quick fox", "visited": [doc["id"] for doc in documents]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 2

    fox_data = response.json()[0]
    assert list(fox_data.keys()) == ["_index", "_id", "_score", "_source", "fields"]
    assert fox_data["_id"] == str(document["id"])
    assert fox_data["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": document["path"],
        "size": document["size"],
        "created_at": document["created_at"].isoformat(),
        "updated_at": document["updated_at"].isoformat(),
        "reach": document["reach"],
        "title": document["title"],
    }
    assert fox_data["fields"] == {"number_of_users": [3], "number_of_groups": [3]}

    other_fox_data = response.json()[1]
    assert list(other_fox_data.keys()) == [
        "_index",
        "_id",
        "_score",
        "_source",
        "fields",
    ]
    assert other_fox_data["_id"] == str(other_fox_document["id"])
    assert other_fox_data["_source"] == {
        "depth": 1,
        "numchild": 0,
        "path": other_fox_document["path"],
        "size": other_fox_document["size"],
        "created_at": other_fox_document["created_at"].isoformat(),
        "updated_at": other_fox_document["updated_at"].isoformat(),
        "reach": other_fox_document["reach"],
        "title": other_fox_document["title"],
    }
    assert other_fox_data["fields"] == {"number_of_users": [3], "number_of_groups": [3]}


@responses.activate
def test_api_documents_search_ordering_by_fields(settings):
    """It should be possible to order by several fields"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.name, documents)

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

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.name, documents)

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

    # Setup: Initialize the service and documents only once
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        2, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.name, documents)

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

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        2, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.name, documents)

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

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.name, documents)

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


# Pagination


@responses.activate
def test_api_documents_search_pagination_basic(settings):
    """Pagination should correctly return documents for the specified page and page size"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        9, reach=random.choice(["public", "authenticated"])
    )
    ids = [str(doc["id"]) for doc in documents]
    prepare_index(service.name, documents)

    # Request the first page with a page size of 3
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "page_number": 1,
            "page_size": 3,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # Page size is 3
    assert [r["_id"] for r in data] == ids[0:3]

    # Request the second page with a page size of 3
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "page_number": 2,
            "page_size": 3,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert [r["_id"] for r in data] == ids[3:6]

    # Request the third page with a page size of 5 (should contain the remaining 3 documents)
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "page_number": 3,
            "page_size": 3,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert [r["_id"] for r in data] == ids[6:9]


@responses.activate
def test_api_documents_search_pagination_last_page_edge_case(settings):
    """Requesting the last page should return the correct number of remaining documents"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        8, reach=random.choice(["public", "authenticated"])
    )
    ids = [str(doc["id"]) for doc in documents]
    prepare_index(service.name, documents)

    # Request the first page with a page size of 3
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "page_number": 1,
            "page_size": 3,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 3
    assert [r["_id"] for r in response.json()] == ids[0:3]

    # Request the third page with a page size of 3 (should contain the last 1 document)
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "page_number": 3,
            "page_size": 3,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 2  # Only 2 documents should be on the last page
    assert [r["_id"] for r in response.json()] == ids[6:]


@responses.activate
def test_api_documents_search_pagination_out_of_bounds(settings):
    """
    Requesting a page number that exceeds the total number of pages should return an empty list
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.name, documents)

    # Request the fourth page with a page size of 2 (there are only 2 pages)
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "page_number": 4,
            "page_size": 2,
            "visited": [doc["id"] for doc in documents],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 0  # No documents should be returned


@responses.activate
def test_api_documents_search_pagination_invalid_parameters(settings):
    """Invalid pagination parameters should result in a 400 error"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(
        4, reach=random.choice(["public", "authenticated"])
    )
    prepare_index(service.name, documents)

    parameters = [
        (
            "invalid",
            10,
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
        ),
        (
            1,
            "invalid",
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
        ),
        (-1, 10, "greater_than_equal", "Input should be greater than or equal to 1"),
        (1, -10, "greater_than_equal", "Input should be greater than or equal to 1"),
        (0, 10, "greater_than_equal", "Input should be greater than or equal to 1"),
        (1, 0, "greater_than_equal", "Input should be greater than or equal to 1"),
    ]

    for page_number, page_size, error_type, error_message in parameters:
        response = APIClient().post(
            "/api/v1.0/documents/search/",
            {"q": "*", "page_number": page_number, "page_size": page_size},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 400
        assert response.data[0]["msg"] == error_message
        assert response.data[0]["type"] == error_type


@responses.activate
def test_api_documents_search_pagination_with_filtering(settings):
    """Pagination should work correctly when combined with filtering by reach"""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    token = build_authorization_bearer()

    service = factories.ServiceFactory(name="test-service")
    public_documents = factories.DocumentSchemaFactory.build_batch(3, reach="public")
    public_ids = [str(doc["id"]) for doc in public_documents]
    private_documents = factories.DocumentSchemaFactory.build_batch(
        2, reach="authenticated"
    )
    prepare_index(service.name, public_documents + private_documents)

    # Filter by public documents, request first page
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "reach": "public",
            "page_number": 1,
            "page_size": 2,
            "visited": public_ids,
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert [r["_id"] for r in response.json()] == public_ids[0:2]

    # Request second page for public documents (remaining 1 document)
    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {
            "q": "*",
            "reach": "public",
            "page_number": 2,
            "page_size": 2,
            "visited": public_ids,
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert [r["_id"] for r in response.json()] == public_ids[2:]
