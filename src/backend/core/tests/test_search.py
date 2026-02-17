"""
Test suite for opensearch search service
"""

import logging
import operator
from json import dumps as json_dumps
from unittest.mock import patch

import pytest
import responses

from core import factories
from core.services import opensearch
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client
from core.services.search import search
from core.utils import bulk_create_documents, delete_search_pipeline, prepare_index

from .mock import albert_embedding_response
from .utils import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_utils,
)
from .utils import (
    enable_hybrid_search,
)

pytestmark = pytest.mark.django_db

SERVICE_NAME = "test-service"


def search_params(service):
    """Build opensearch.search() parameters for tests using the service index name"""
    return {
        "nb_results": 20,
        "order_by": "relevance",
        "order_direction": "desc",
        "search_indices": {service.index_name},
        "reach": None,
        "user_sub": "user_sub",
        "groups": [],
        "visited": [],
        "tags": [],
    }


@pytest.fixture(autouse=True)
def before_each():
    """Clear caches and delete search pipeline before each test"""
    clear_caches()
    yield
    clear_caches()


def clear_caches():
    """Clear caches used in opensearch service and factories"""
    check_hybrid_search_enabled.cache_clear()
    # the instance of check_hybrid_search_enabled used in utils.py
    # is different and must be cleared separately
    check_hybrid_search_enabled_utils.cache_clear()
    delete_search_pipeline()
    opensearch_client().indices.delete(index="*")


@responses.activate
def test_hybrid_search_success(settings, caplog):
    """Test the hybrid search is successful"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    q = "canine pet"
    with caplog.at_level(logging.INFO):
        result = search(q=q, **search_params(service))

    assert any(
        f"Performing hybrid search with embedding: {q}" in message
        for message in caplog.messages
    )

    assert result["hits"]["max_score"] > 0.0
    # hybrid search always returns a response of fixed sized sorted and scored by relevance
    assert {hit["_source"]["title.en"] for hit in result["hits"]["hits"]} == {
        doc["title"] for doc in documents
    }


@responses.activate
def test_hybrid_search_without_embedded_index(settings, caplog):
    """Test the hybrid search is successful"""
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves"},
            {"title": "dog", "content": "dogs"},
            {"title": "cat", "content": "cats"},
        ]
    )
    # index is prepared but hybrid search is not yet enable.
    # they then won't be embedded.
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    # check embedding is None
    indexed_documents = opensearch.opensearch_client().search(
        index=service.index_name, body={"query": {"match_all": {}}}
    )
    assert indexed_documents["hits"]["hits"][0]["_source"]["chunks"] is None

    # hybrid search is enabled before to do the first requests
    enable_hybrid_search(settings)

    q = "canine pet"
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    with caplog.at_level(logging.INFO):
        result = search(q=q, **search_params(service))

    # the hybrid search is done successfully
    assert any(
        f"Performing hybrid search with embedding: {q}" in message
        for message in caplog.messages
    )

    # but no match can obviously be found
    assert result["hits"]["max_score"] == 0.0
    assert len(result["hits"]["hits"]) == 0

    # The full-text search is still functional
    q = "wolf"
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    with caplog.at_level(logging.INFO):
        result = search(q=q, **search_params(service))

    assert any(
        f"Performing hybrid search with embedding: {q}" in message
        for message in caplog.messages
    )

    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 1
    assert (
        result["hits"]["hits"][0]["_source"][
            f"title.{settings.UNDETERMINED_LANGUAGE_CODE}"
        ]
        == q
    )


def test_fall_back_on_full_text_search_if_hybrid_search_disabled(settings, caplog):
    """Test the full-text search is done when HYBRID_SEARCH_ENABLED=False"""
    enable_hybrid_search(settings)
    settings.HYBRID_SEARCH_ENABLED = False
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    q = "wolf"
    with caplog.at_level(logging.INFO):
        result = search(q=q, **search_params(service))

    assert any(
        "Hybrid search is disabled via HYBRID_SEARCH_ENABLED setting" in message
        for message in caplog.messages
    )
    assert any(
        f"Performing full-text search without embedding: {q}" in message
        for message in caplog.messages
    )

    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 1
    assert result["hits"]["hits"][0]["_source"]["title.en"] == "wolf"


@responses.activate
def test_fall_back_on_full_text_search_if_embedding_api_fails(settings, caplog):
    """Test the full-text search is done when the embedding api fails"""

    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        status=401,
        body=json_dumps({"message": "Authentication failed."}),
    )
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    q = "wolf"
    with caplog.at_level(logging.INFO):
        result = search(q=q, **search_params(service))

    assert any(
        "embedding API request failed: 401 Client Error: Unauthorized" in message
        for message in caplog.messages
    )
    assert any(
        f"Performing full-text search without embedding: {q}" in message
        for message in caplog.messages
    )
    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 1
    assert result["hits"]["hits"][0]["_source"]["title.en"] == "wolf"


@responses.activate
def test_fall_back_on_full_text_search_if_variable_are_missing(settings, caplog):
    """Test the full-text search is done when variables are missing for hybrid search"""
    enable_hybrid_search(settings)
    del settings.HYBRID_SEARCH_WEIGHTS
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    q = "wolf"
    with caplog.at_level(logging.INFO):
        result = search(q=q, **search_params(service))

    assert any(
        "Missing variables for hybrid search: HYBRID_SEARCH_WEIGHTS" in message
        for message in caplog.messages
    )
    assert any(
        f"Performing full-text search without embedding: {q}" in message
        for message in caplog.messages
    )
    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 1
    assert result["hits"]["hits"][0]["_source"]["title.en"] == "wolf"


@responses.activate
def test_match_all(settings, caplog):
    """Test match all when q='*' and no semantic search is needed"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
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


@responses.activate
def test_search_ordering_by_relevance(settings, caplog):
    """Test the hybrid supports ordering by relevance asc and desc"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    q = "canine pet"
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    for direction in ["asc", "desc"]:
        with caplog.at_level(logging.INFO):
            result = search(
                q=q, **{**search_params(service), "order_direction": direction}
            )

        # Check that results are sorted by score as expected
        hits = result["hits"]["hits"]
        compare = operator.le if direction == "asc" else operator.ge
        for i in range(len(hits) - 1):
            assert compare(hits[i]["_score"], hits[i + 1]["_score"])


@responses.activate
def test_hybrid_search_number_of_matches(settings):
    """
    In this test full-text search always return 0 documents.
    The test checks the number of hits returned by hybrid search with different k values.
    """
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    q = "pony"  # full-text matches 0 document
    for nb_results in [1, 2, 3]:  # semantic should match k documents
        result = search(q=q, **{**search_params(service), "nb_results": nb_results})
        assert len(result["hits"]["hits"]) == nb_results


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


# pylint: disable=too-many-arguments, too-many-positional-arguments
@responses.activate
@patch("core.services.search.rerank")
@pytest.mark.parametrize(
    "rerank_requested, reranker_enabled, rerank_called, caplog_messages",
    [
        (True, True, True, []),
        (
            True,
            False,
            False,
            [
                "Reranking was explicitly requested but the reranker is "
                "disabled in settings. Reranking skipped."
            ],
        ),
        (False, True, False, []),
        (False, False, False, []),
        (None, False, False, []),
        (None, True, True, []),
    ],
)
def test_search_rerank(  # noqa : PLR0913
    mock_rerank,
    rerank_requested,
    reranker_enabled,
    rerank_called,
    caplog_messages,
    settings,
    caplog,
):
    """Test that rerank activation according to args and settings"""
    settings.RERANKER_ENABLED = reranker_enabled

    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    mock_rerank.return_value = documents
    service = factories.ServiceFactory(name=SERVICE_NAME)
    prepare_index(service.index_name, documents)

    with caplog.at_level(logging.INFO):
        search(
            q="canine pet", rerank_requested=rerank_requested, **search_params(service)
        )

    assert mock_rerank.called == rerank_called
    for message in caplog_messages:
        assert message in caplog.text
