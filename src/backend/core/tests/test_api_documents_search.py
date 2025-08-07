"""
Test suite for searching documents in OpenSearch over the API.

Don't use pytest parametrized tests because batch generation and indexing
of documents is slow and better done only once.
"""

import operator

import pytest

from rest_framework.test import APIClient

from core import enums, factories

from .utils import prepare_index

pytestmark = pytest.mark.django_db


def test_api_documents_search_query_title():
    """Searching a document by its title should work as expected"""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build(
        title="The quick brown fox", content="the wolf"
    )

    # Add other documents
    other_fox_document = factories.DocumentSchemaFactory.build(
        title="The blue fox", content="the wolf"
    )
    no_fox_document = factories.DocumentSchemaFactory.build(
        title="The brown goat", content="the wolf"
    )
    documents = [document, other_fox_document, no_fox_document]
    prepare_index(service.name, documents)

    response = APIClient().get(
        "/api/v1.0/documents/",
        {"q": "a quick fox"},
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
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


def test_api_documents_search_query_content():
    """Searching a document by its content should work as expected"""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build(
        title="the wolf", content="The quick brown fox"
    )

    # Add other documents
    other_fox_document = factories.DocumentSchemaFactory.build(
        title="the wolf", content="The blue fox"
    )
    no_fox_document = factories.DocumentSchemaFactory.build(
        title="the wolf", content="The brown goat"
    )
    prepare_index(service.name, [document, other_fox_document, no_fox_document])

    response = APIClient().get(
        "/api/v1.0/documents/",
        {"q": "a quick fox"},
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
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


def test_api_documents_search_ordering_by_fields():
    """It should be possible to order by several fields"""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(4)
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
        response = APIClient().get(
            f"/api/v1.0/documents/?q=*&order_by={field}&order_direction={direction}",
            HTTP_AUTHORIZATION=f"Bearer {service.token}",
        )

        assert response.status_code == 200
        responses = response.json()
        assert len(responses) == 4

        # Check that results are sorted by the field as expected
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(responses) - 1):
            assert compare(
                responses[i]["_source"][field], responses[i + 1]["_source"][field]
            )


def test_api_documents_search_ordering_by_relevance():
    """It should be possible to order by relevance (score)"""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(4)
    prepare_index(service.name, documents)

    for direction in ["asc", "desc"]:
        response = APIClient().get(
            f"/api/v1.0/documents/?q=*&order_by=relevance&order_direction={direction}",
            HTTP_AUTHORIZATION=f"Bearer {service.token}",
        )

        assert response.status_code == 200
        responses = response.json()
        assert len(responses) == 4

        # Check that results are sorted by score as expected
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(responses) - 1):
            assert compare(responses[i]["_score"], responses[i + 1]["_score"])


def test_api_documents_search_ordering_by_unknown_field():
    """Trying to sort by an unknown field should return a 400 error"""

    # Setup: Initialize the service and documents only once
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(2)
    prepare_index(service.name, documents)

    # Define the parameters manually
    directions = ["asc", "desc"]

    # Perform the parameterized tests
    for direction in directions:
        response = APIClient().get(
            f"/api/v1.0/documents/?q=*&order_by=unknown&order_direction={direction}",
            HTTP_AUTHORIZATION=f"Bearer {service.token}",
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


def test_api_documents_search_ordering_by_unknown_direction():
    """Trying to sort with an unknown direction should return a 400 error"""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(2)
    prepare_index(service.name, documents)

    for field in enums.ORDER_BY_OPTIONS:
        response = APIClient().get(
            f"/api/v1.0/documents/?q=*&order_by={field}&order_direction=unknown",
            HTTP_AUTHORIZATION=f"Bearer {service.token}",
        )

        assert response.status_code == 400
        assert response.json() == [
            {
                "loc": ["order_direction"],
                "msg": "Input should be 'asc' or 'desc'",
                "type": "literal_error",
            }
        ]


def test_api_documents_search_filtering_by_reach():
    """It should be possible to filter results by their reach"""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(4)
    prepare_index(service.name, documents)

    for reach in enums.ReachEnum:
        response = APIClient().get(
            f"/api/v1.0/documents/?q=*&reach={reach.value}",
            HTTP_AUTHORIZATION=f"Bearer {service.token}",
        )

        assert response.status_code == 200
        responses = response.json()

        for result in responses:
            assert reach == result["_source"]["reach"]


# Pagination


def test_api_documents_search_pagination_basic():
    """Pagination should correctly return documents for the specified page and page size"""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(9)
    ids = [str(doc["id"]) for doc in documents]
    prepare_index(service.name, documents)

    # Request the first page with a page size of 3
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&page_number=1&page_size=3",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )
    assert response.status_code == 200
    responses = response.json()
    assert len(responses) == 3  # Page size is 3
    assert [r["_id"] for r in responses] == ids[0:3]

    # Request the second page with a page size of 3
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&page_number=2&page_size=3",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )
    assert response.status_code == 200
    responses = response.json()
    assert len(responses) == 3
    assert [r["_id"] for r in responses] == ids[3:6]

    # Request the third page with a page size of 5 (should contain the remaining 3 documents)
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&page_number=3&page_size=3",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    responses = response.json()
    assert len(responses) == 3
    assert [r["_id"] for r in responses] == ids[6:9]


def test_api_documents_search_pagination_last_page_edge_case():
    """Requesting the last page should return the correct number of remaining documents"""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(8)
    ids = [str(doc["id"]) for doc in documents]
    prepare_index(service.name, documents)

    # Request the first page with a page size of 3
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&page_number=1&page_size=3",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 3
    assert [r["_id"] for r in response.json()] == ids[0:3]

    # Request the third page with a page size of 3 (should contain the last 1 document)
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&page_number=3&page_size=3",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 2  # Only 2 documents should be on the last page
    assert [r["_id"] for r in response.json()] == ids[6:]


def test_api_documents_search_pagination_out_of_bounds():
    """
    Requesting a page number that exceeds the total number of pages should return an empty list
    """
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(4)
    prepare_index(service.name, documents)

    # Request the fourth page with a page size of 2 (there are only 2 pages)
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&page_number=4&page_size=2",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 0  # No documents should be returned


def test_api_documents_search_pagination_invalid_parameters():
    """Invalid pagination parameters should result in a 400 error"""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(4)
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
        response = APIClient().get(
            f"/api/v1.0/documents/?q=*&page_number={page_number}&page_size={page_size}",
            HTTP_AUTHORIZATION=f"Bearer {service.token}",
        )

        assert response.status_code == 400
        assert response.data[0]["msg"] == error_message
        assert response.data[0]["type"] == error_type


def test_api_documents_search_pagination_with_filtering():
    """Pagination should work correctly when combined with filtering by reach"""
    service = factories.ServiceFactory(name="test-service")
    public_documents = factories.DocumentSchemaFactory.build_batch(3, reach="public")
    public_ids = [str(doc["id"]) for doc in public_documents]
    private_documents = factories.DocumentSchemaFactory.build_batch(
        2, reach="authenticated"
    )
    prepare_index(service.name, public_documents + private_documents)

    # Filter by public documents, request first page
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&reach=public&page_number=1&page_size=2",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert [r["_id"] for r in response.json()] == public_ids[0:2]

    # Request second page for public documents (remaining 1 document)
    response = APIClient().get(
        "/api/v1.0/documents/?q=*&reach=public&page_number=2&page_size=2",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert [r["_id"] for r in response.json()] == public_ids[2:]
