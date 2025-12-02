"""
Unit test for `reindex_with_embedding` command.
"""

from unittest.mock import patch

from django.core.management import CommandError, call_command

import pytest
import responses

from core.management.commands.reindex_with_embedding import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_command,
)
from core.management.commands.reindex_with_embedding import (
    reindex_with_embedding,
)
from core.models import get_opensearch_index_name
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client
from core.tests.mock import albert_embedding_response
from core.tests.utils import (
    enable_hybrid_search,
)
from core.utils import bulk_create_documents, delete_search_pipeline, prepare_index

SERVICE_NAME = "test-index"


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
    check_hybrid_search_enabled_command.cache_clear()
    delete_search_pipeline()


@responses.activate
def test_reindex_with_embedding_command(settings):
    """Test command create indexes with embedding and search pipeline"""
    # create documents and index them with hybrid search disabled
    opensearch_client_ = opensearch_client()
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    index_name = get_opensearch_index_name(SERVICE_NAME)
    prepare_index(index_name, documents)

    # the index has not been embedded in the initial state
    initial_index = opensearch_client_.search(
        index=index_name, size=3, body={"query": {"match_all": {}}}
    )
    assert len(initial_index["hits"]["hits"]) == 3
    for embedded_hit in initial_index["hits"]["hits"]:
        assert embedded_hit["_source"]["embedding"] == None
        assert embedded_hit["_source"]["embedding_model"] is None

    # enable hybrid search
    enable_hybrid_search(settings)
    check_hybrid_search_enabled_command.cache_clear()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    call_command("reindex_with_embedding", SERVICE_NAME)

    opensearch_client_.indices.refresh(index=index_name)
    embedded_index = opensearch_client_.search(
        index=index_name, size=3, body={"query": {"match_all": {}}}
    )

    # the source index has been replaced with embedding version
    assert len(embedded_index["hits"]["hits"]) == 3
    for embedded_hit in embedded_index["hits"]["hits"]:
        embedded_source = embedded_hit["_source"]
        # the index contains a embedding and embedding_model
        assert (
            embedded_source["embedding"]
            == albert_embedding_response.response["data"][0]["embedding"]
        )
        assert embedded_source["embedding_model"] == settings.EMBEDDING_API_MODEL_NAME
        # assert initial value have not been effected
        initial_hits = [
            hit_
            for hit_ in initial_index["hits"]["hits"]
            if hit_["_id"] == embedded_hit["_id"]
        ]
        assert len(initial_hits) == 1
        initial_source = initial_hits[0]["_source"]
        assert initial_source["title.en-us"] == embedded_source["title.en-us"]
        assert initial_source["content.en-us"] == embedded_source["content.en-us"]
        assert initial_source["created_at"] == embedded_source["created_at"]
        assert initial_source["users"] == embedded_source["users"]


@responses.activate
def test_reindex_can_fail_and_restart(settings):
    """Test command handles embedding errors gracefully and continues processing."""
    opensearch_client_ = opensearch_client()
    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    index_name = get_opensearch_index_name(SERVICE_NAME)
    prepare_index(index_name, documents)

    # enable hybrid search after first indexing
    enable_hybrid_search(settings)
    check_hybrid_search_enabled_command.cache_clear()

    # First call succeeds, second fails, third succeeds
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json={"error": "rate limit exceeded"},
        status=429,
    )
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    result = reindex_with_embedding(index_name)

    # assert results reflect 2 successes and 1 failure
    assert result["nb_success_embedding"] == 2
    assert result["nb_failed_embedding"] == 1

    # assert the index state
    opensearch_client_.indices.refresh(index=index_name)
    embedded_index = opensearch_client_.search(
        index=index_name, size=3, body={"query": {"match_all": {}}}
    )
    # Should have 2 documents with embeddings, 1 without due to error
    embedded_count = 0
    not_embedded_count = 0
    for hit in embedded_index["hits"]["hits"]:
        if hit["_source"].get("embedding"):
            embedded_count += 1
            assert (
                hit["_source"]["embedding_model"] == settings.EMBEDDING_API_MODEL_NAME
            )
        else:
            not_embedded_count += 1
            assert hit["_source"]["embedding_model"] is None
    assert embedded_count == 2
    assert not_embedded_count == 1

    # the command can be run again to index failed items
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    result = reindex_with_embedding(index_name)

    # assert results
    assert result["nb_success_embedding"] == 1
    assert result["nb_failed_embedding"] == 0

    # assert there is now 1 more success and 0 failures
    opensearch_client_.indices.refresh(index=index_name)
    embedded_index = opensearch_client_.search(
        index=index_name, size=3, body={"query": {"match_all": {}}}
    )
    for hit in embedded_index["hits"]["hits"]:
        assert (
            hit["_source"]["embedding"]
            == albert_embedding_response.response["data"][0]["embedding"]
        )
        assert hit["_source"]["embedding_model"] == settings.EMBEDDING_API_MODEL_NAME


@responses.activate
def test_reindex_preserves_concurrent_updates(settings):
    """
    Test that concurrent document updates don't get overwritten by reindexing.
    This test simulates the following scenario:
    • the hybrid search is disabled
    • documents are created and indexed without indexing
    • the hybrid search is enabled
    • the reindexing is triggered
    • one document is updated while the reindexing is still running
    Because the updated document is modified after the hybrid search is enabled,
    it has properly been indexed with embedding, the reindexing command must
    ignore this document to preserve this latest update.
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

    updated_title = "updated dog"
    updated_embedding = [
        1.0
    ] * settings.EMBEDDING_DIMENSION  # dummy embedding to simulate concurrent update
    # add a side_effect on the search to simulate a concurrent update
    patch(
        "core.services.opensearch.opensearch_client_.search",
        side_effect=opensearch_client_.update(
            index=index_name,
            id=documents[1]["id"],
            body={
                "doc": {
                    "title.en-us": updated_title,
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
    result = reindex_with_embedding(index_name)
    assert result["nb_success_embedding"] == 2
    assert result["nb_failed_embedding"] == 0

    opensearch_client_.indices.refresh(index=index_name)
    embedded_index = opensearch_client_.search(
        index=index_name, size=2, body={"query": {"match_all": {}}}
    )
    # Check that the latest update is preserved
    dog_doc = [
        hit
        for hit in embedded_index["hits"]["hits"]
        if hit["_source"]["title.en-us"] == updated_title
    ]
    assert len(dog_doc) == 1
    assert dog_doc[0]["_source"]["embedding"] is None
    assert dog_doc[0]["_source"]["embedding_model"] is None


def test_reindex_command_but_hybrid_search_is_disabled():
    """Test the `reindex_with_embedding` command fails when hybrid search is disabled."""
    with pytest.raises(CommandError) as err:
        call_command("reindex_with_embedding", SERVICE_NAME)

    assert str(err.value) == "Hybrid search is not enabled or properly configured."


def test_reindex_command_but_index_does_not_exist(settings):
    """Test the `reindex_with_embedding` command fails when the idex does not exist."""
    wrong_index = "wrong-index-name"
    enable_hybrid_search(settings)

    wrong_index_name = get_opensearch_index_name(wrong_index)

    with pytest.raises(CommandError) as err:
        call_command("reindex_with_embedding", wrong_index)

    assert str(err.value) == f"Index {wrong_index_name} does not exist."
