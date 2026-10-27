"""
Test suite for opensearch search service
"""

import logging
import operator

import pytest

from core import factories
from core.services.search import search
from core.utils import prepare_index

from .utils import bulk_create_documents

pytestmark = pytest.mark.django_db

SERVICE_NAME = "test-service"


def search_params(service):
    """Build search() parameters for tests using the service index name"""
    return {
        "nb_results": 20,
        "order_by": "relevance",
        "order_direction": "desc",
        "search_indices": [service.index_name],
        "reach": None,
        "user_sub": "user_sub",
        "groups": [],
        "visited": [],
        "tags": [],
    }


def test_match_all(caplog):
    """Test match all when q='*'"""
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    q = "*"
    with caplog.at_level(logging.INFO):
        result = search(q=q, **search_params(service))

    assert any("Performing match_all query" in message for message in caplog.messages)
    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 3


def test_search_ordering_by_relevance():
    """Test the search supports ordering by relevance asc and desc"""
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "wolf dog", "content": "wolfdogs are wolves crossed with dogs"},
        ]
    )
    q = "wolves dogs"
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    for direction in ["asc", "desc"]:
        result = search(q=q, **{**search_params(service), "order_direction": direction})

        # Check that results are sorted by score as expected
        hits = result["hits"]["hits"]
        assert len(hits) == 3
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(hits) - 1):
            assert compare(hits[i]["_score"], hits[i + 1]["_score"])


def test_search_filtering_by_single_tag():
    """Test filtering documents by a single tag"""
    service = factories.ServiceFactory(name=SERVICE_NAME)

    documents_to_search = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-search"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-search", "tag-to-filter"]
        ),
    ]
    documents_to_filter = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-filter"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
        ),
    ]
    expected_ids = {str(doc["id"]) for doc in documents_to_search}

    prepare_index(service.index_name, documents_to_search + documents_to_filter)

    # Search for documents with tag-to-search tag
    result = search(q="*", **{**search_params(service), "tags": ["tag-to-search"]})
    returned_ids = {hit["_id"] for hit in result["hits"]["hits"]}

    assert result["hits"]["total"]["value"] == len(documents_to_search)
    assert returned_ids == expected_ids


def test_search_filtering_by_multiple_tags():
    """Test filtering documents by multiple tags (OR logic)"""
    service = factories.ServiceFactory(name=SERVICE_NAME)

    documents_to_search = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-search-1"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-search-1", "tag-to-filter"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-search-2", "tag-to-filter"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-search-1", "tag-to-search-2"]
        ),
    ]
    documents_to_filter = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["tag-to-filter"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
        ),
    ]
    expected_ids = {str(doc["id"]) for doc in documents_to_search}

    prepare_index(service.index_name, documents_to_search + documents_to_filter)

    # Search for documents with tag-to-search-1 OR tag-to-search-2 tags
    result = search(
        q="*",
        **{**search_params(service), "tags": ["tag-to-search-1", "tag-to-search-2"]},
    )
    returned_ids = {hit["_id"] for hit in result["hits"]["hits"]}

    assert result["hits"]["total"]["value"] == len(documents_to_search)
    assert returned_ids == expected_ids


def test_search_no_tags_filter_returns_all():
    """Test that not providing tags filter returns all documents"""
    service = factories.ServiceFactory(name=SERVICE_NAME)

    documents = bulk_create_documents(
        [
            {
                "title": "Document without tags",
                "content": "Untagged document",
            },
            {
                "title": "Document with tags",
                "content": "Tagged document",
                "tags": ["tag-to-search"],
            },
        ]
    )
    prepare_index(service.index_name, documents)

    # Search without tags filter
    result = search(q="*", **search_params(service))

    assert result["hits"]["total"]["value"] == len(documents)


def test_search_filtering_by_tag_and_query():
    """Test filtering documents by both tag and query text"""
    service = factories.ServiceFactory(name=SERVICE_NAME)

    documents_to_search = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], title="title to search", tags=["tag-to-search"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 1",
            tags=["tag-to-search", "tag-to-filter"],
        ),
    ]
    documents_to_filter = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], title="title to filter", tags=["tag-to-filter"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], title="title to filter 1", tags=["tag-to-filter"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 2",
        ),
    ]
    expected_ids = {str(doc["id"]) for doc in documents_to_search}

    prepare_index(service.index_name, documents_to_search + documents_to_filter)

    # Search with both query and tag filter
    result = search(q="search", **{**search_params(service), "tags": ["tag-to-search"]})
    returned_ids = {hit["_id"] for hit in result["hits"]["hits"]}

    assert result["hits"]["total"]["value"] == len(documents_to_search)
    assert returned_ids == expected_ids


def test_search_filtering_by_path():
    """Test filtering documents by path prefix"""
    service = factories.ServiceFactory(name=SERVICE_NAME)

    documents_to_search = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], path="path/to/search/doc-1"
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], path="path/to/search/doc-2"
        ),
    ]
    documents_to_filter = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], path="path/to/filter/doc-3"
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
        ),
    ]
    expected_ids = {str(doc["id"]) for doc in documents_to_search}

    prepare_index(service.index_name, documents_to_search + documents_to_filter)

    path_filter = "path/to/search"
    result = search(q="*", **{**search_params(service), "path": path_filter})
    returned_ids = {hit["_id"] for hit in result["hits"]["hits"]}

    assert result["hits"]["total"]["value"] == len(documents_to_search)
    assert returned_ids == expected_ids


def test_search_filtering_by_query_path_and_tag():
    """Test filtering documents by query text, path prefix and tag combined"""
    service = factories.ServiceFactory(name=SERVICE_NAME)

    documents_to_search = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 0",
            path="path/to/search-0",
            tags=["tag-to-search"],
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 1",
            path="path/to/search/doc1",
            tags=["tag-to-search", "tag-to-filter"],
        ),
    ]
    documents_to_filter = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to filter",
            path="path/to/search/doc-3",
            tags=["tag-to-search"],
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 4",
            path="path/to/filter/doc-4",
            tags=["tag-to-search"],
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 4",
            path="path/to/search/doc-4",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], title="title to search 5", tags=["tag-to-search"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 6",
            path="path/to/search/doc-6",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="title to search 7",
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"],
            title="",
            path="path/to/search/doc-8",
            tags=["tag-to-search"],
        ),
    ]
    expected_ids = {str(doc["id"]) for doc in documents_to_search}

    prepare_index(service.index_name, documents_to_search + documents_to_filter)

    # Search with query, path and tag filters combined
    result = search(
        q="search",
        **{
            **search_params(service),
            "path": "path/to/search",
            "tags": ["tag-to-search"],
        },
    )
    returned_ids = {hit["_id"] for hit in result["hits"]["hits"]}

    assert result["hits"]["total"]["value"] == len(documents_to_search)
    assert returned_ids == expected_ids
