"""
Test suite for reindex service
"""

import logging
from unittest.mock import patch

import pytest
import responses

from core.enums import IndexingStatusEnum
from core.models import get_opensearch_index_name
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client
from core.services.reindex import reindex_with_embedding
from core.tests.mock import albert_embedding_response
from core.tests.utils import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_utils,
)
from core.tests.utils import enable_hybrid_search, prepare_index
from core.utils import bulk_create_documents

pytestmark = pytest.mark.django_db

SERVICE_NAME = "test-reindex-service"


@pytest.fixture(autouse=True)
def before_each():
    """Clear caches before each test"""
    clear_caches()
    yield
    clear_caches()


def clear_caches():
    """Clear caches used in opensearch service and factories"""
    check_hybrid_search_enabled.cache_clear()
    check_hybrid_search_enabled_utils.cache_clear()


@responses.activate
def test_reindex_with_embedding_success(settings):
    """Test reindex_with_embedding successfully chunks and embeds documents"""
    enable_hybrid_search(settings)
    opensearch_client_ = opensearch_client()
    settings.CHUNK_SIZE = 50
    settings.CHUNK_OVERLAP = 5

    # Create documents with varying content lengths
    documents = bulk_create_documents(
        [
            {
                "title": "Doc 0",
                "content": "doc 1.",
            },
            {
                "title": "Doc 1",
                "content": "doc 1",  # Long enough to require chunking
            },
            {
                "title": "Doc 2",
                "content": "doc 2",
            },
        ]
    )

    index_name = get_opensearch_index_name(SERVICE_NAME)
    prepare_index(index_name, documents)

    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    # Execute reindexing
    result = reindex_with_embedding(
        index_name,
        {"match_all": {}},  # Reindex all documents
        batch_size=10,
    )

    # Verify results
    assert result["nb_success_embedding"] == 3
    assert result["nb_failed_embedding"] == 0

    # Verify documents in index
    opensearch_client_.indices.refresh(index=index_name)
    response = opensearch_client_.search(
        index=index_name, body={"query": {"match_all": {}}}
    )

    assert len(response["hits"]["hits"]) == 3

    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        # All documents should now have chunks and embedding_model
        assert source["embedding_model"] == settings.EMBEDDING_API_MODEL_NAME
        assert source["indexing_status"] == IndexingStatusEnum.READY

        assert source["chunks"] is not None
        for chunk in source["chunks"]:
            assert "index" in chunk
            assert "content" in chunk
            assert "embedding" in chunk
            assert (
                chunk["embedding"]
                == albert_embedding_response.response["data"][0]["embedding"]
            )


@responses.activate
def test_reindex_with_embedding_partial_failure(caplog, settings):
    """Test reindex_with_embedding handles partial failures correctly"""
    opensearch_client_ = opensearch_client()

    documents = bulk_create_documents(
        [
            {"title": "Doc 0", "content": "Content for document 0"},
            {"title": "Doc 1", "content": "Content for document 1"},
            {"title": "Doc 2", "content": "Content for document 2"},
        ]
    )

    index_name = get_opensearch_index_name(SERVICE_NAME)
    prepare_index(index_name, documents, embedding_enabled=False)

    enable_hybrid_search(settings)
    check_hybrid_search_enabled.cache_clear()

    # Mock API: first call succeeds, second fails, third succeeds
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json={"error": "Rate limit exceeded"},
        status=429,
    )
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    with caplog.at_level(logging.WARNING):
        result = reindex_with_embedding(index_name, {"match_all": {}}, batch_size=10)

    # Verify results: 2 successes, 1 failure
    assert result["nb_success_embedding"] == 2
    assert result["nb_failed_embedding"] == 1

    assert any("Failed to embed chunk" in message for message in caplog.messages)

    # Verify index state
    opensearch_client_.indices.refresh(index=index_name)
    doc_0 = opensearch_client_.get(index=index_name, id=documents[0]["id"])
    doc_1 = opensearch_client_.get(index=index_name, id=documents[1]["id"])
    doc_2 = opensearch_client_.get(index=index_name, id=documents[2]["id"])

    assert doc_0["_source"]["embedding_model"] == settings.EMBEDDING_API_MODEL_NAME
    assert doc_0["_source"]["chunks"] is not None
    assert doc_1["_source"].get("embedding_model") is None
    assert doc_1["_source"].get("chunks") is None
    assert doc_2["_source"]["embedding_model"] == settings.EMBEDDING_API_MODEL_NAME
    assert doc_2["_source"]["chunks"] is not None


@responses.activate
def test_reindex_with_embedding_preserves_concurrent_updates(settings):
    """
    Test that concurrent document updates don't get overwritten by reindexing.
    Because the updated document is modified after indexing (seq_no changed),
    the reindexing command must skip this document to preserve the latest update.
    """
    opensearch_client_ = opensearch_client()

    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
        ]
    )

    index_name = get_opensearch_index_name(SERVICE_NAME)
    prepare_index(index_name, documents)
    enable_hybrid_search(settings)

    check_hybrid_search_enabled.cache_clear()

    updated_title = "updated dog"
    patch(
        "core.services.search.search",
        side_effect=opensearch_client_.update(
            index=index_name,
            id=documents[1]["id"],
            body={
                "doc": {
                    "title.en": updated_title,
                }
            },
        ),
    )

    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    result = reindex_with_embedding(index_name, {"match_all": {}}, batch_size=10)

    assert result["nb_success_embedding"] == 2
    assert result["nb_failed_embedding"] == 0

    # Verify the concurrent update was preserved
    updated_doc = opensearch_client_.get(index=index_name, id=documents[1]["id"])
    assert updated_doc["_source"]["title.en"] == updated_title
    assert updated_doc["_source"]["chunks"] is None
    assert updated_doc["_source"]["embedding_model"] is None


@responses.activate
def test_reindex_with_embedding_empty_result(settings):
    """Test reindex_with_embedding with query that matches no documents"""
    documents = bulk_create_documents([{"title": "Doc 1", "content": "Content 1"}])

    index_name = get_opensearch_index_name(SERVICE_NAME)
    prepare_index(index_name, documents)

    enable_hybrid_search(settings)
    check_hybrid_search_enabled.cache_clear()

    # Query that matches nothing
    result = reindex_with_embedding(
        index_name, {"term": {"title.en": "nonexistent"}}, batch_size=10
    )

    # No documents should be processed
    assert result["nb_success_embedding"] == 0
    assert result["nb_failed_embedding"] == 0

    opensearch_client_ = opensearch_client()
    opensearch_client_.indices.refresh(index=index_name)
    document = opensearch_client_.get(index=index_name, id=documents[0]["id"])
    assert document["_source"]["embedding_model"] is None
    assert document["_source"]["chunks"] is None
