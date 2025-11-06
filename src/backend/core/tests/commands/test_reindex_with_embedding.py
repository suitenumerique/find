"""
Unit test for `reindex_with_embedding` command.
"""

from django.core.management import CommandError, call_command

import pytest
import responses

from core.management.commands.reindex_with_embedding import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_command,
)
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client
from core.tests.mock import albert_embedding_response
from core.tests.utils import (
    bulk_create_documents,
    delete_search_pipeline,
    delete_test_indices,
    enable_hybrid_search,
    prepare_index,
)

SOURCE_INDEX_NAME = "test-index"
DESTINATION_INDEX_NAME = "test-index-embedded"


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
    delete_test_indices()


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
    prepare_index(SOURCE_INDEX_NAME, documents)

    # the index has not been embedded in the initial state
    initial_index = opensearch_client_.search(
        index=SOURCE_INDEX_NAME, size=3, body={"query": {"match_all": {}}}
    )
    assert len(initial_index["hits"]["hits"]) == 3
    for embedded_hit in initial_index["hits"]["hits"]:
        assert embedded_hit["_source"]["embedding"] == None
        assert "embedding_model" not in embedded_hit["_source"]

    # enable hybrid search
    enable_hybrid_search(settings)
    check_hybrid_search_enabled_command.cache_clear()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    # call the command
    call_command("reindex_with_embedding", SOURCE_INDEX_NAME)

    opensearch_client_.indices.refresh(index=SOURCE_INDEX_NAME)
    embedded_index = opensearch_client_.search(
        index=SOURCE_INDEX_NAME, size=3, body={"query": {"match_all": {}}}
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
        assert initial_source["title"] == embedded_source["title"]
        assert initial_source["content"] == embedded_source["content"]
        assert initial_source["created_at"] == embedded_source["created_at"]
        assert initial_source["users"] == embedded_source["users"]


def test_reindex_command_but_hybrid_search_is_disabled():
    """Test the `reindex_with_embedding` command fails when hybrid search is disabled."""
    with pytest.raises(CommandError) as err:
        call_command("reindex_with_embedding", SOURCE_INDEX_NAME)

    assert str(err.value) == "Hybrid search is not enabled or properly configured."


def test_reindex_command_but_index_does_not_exist(settings):
    """Test the `reindex_with_embedding` command fails when the idex does not exist."""
    wrong_index = "wrong-index-name"
    enable_hybrid_search(settings)

    with pytest.raises(CommandError) as err:
        call_command("reindex_with_embedding", wrong_index)

    assert str(err.value) == f"Index {wrong_index} does not exist."
