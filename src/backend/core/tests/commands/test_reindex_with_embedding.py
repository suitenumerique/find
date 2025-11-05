"""
Unit test for `reindex_with_embedding` command.
"""

from django.core.management import CommandError, call_command

import pytest
import responses

from core.management.commands.reindex_with_embedding import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_command,
)
from core.management.commands.reindex_with_embedding import (
    reindex_with_embedding,
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

    # enable hybrid search
    enable_hybrid_search(settings)
    check_hybrid_search_enabled_command.cache_clear()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    call_command("reindex_with_embedding", SOURCE_INDEX_NAME)

    opensearch_client_.indices.refresh(index=SOURCE_INDEX_NAME)
    source_index = opensearch_client_.search(
        index=SOURCE_INDEX_NAME, size=3, body={"query": {"match_all": {}}}
    )

    # the source index has been replaced with embedding version
    assert len(source_index["hits"]["hits"]) == 3
    for hit in source_index["hits"]["hits"]:
        assert (
            hit["_source"]["embedding"]
            == albert_embedding_response.response["data"][0]["embedding"]
        )


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

    assert str(err.value) == f"Source index {wrong_index} does not exist."


@responses.activate
def test_reindex_with_embedding(settings):
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

    # enable hybrid search
    enable_hybrid_search(settings)
    check_hybrid_search_enabled_command.cache_clear()
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    reindex_with_embedding(
        opensearch_client_, SOURCE_INDEX_NAME, DESTINATION_INDEX_NAME
    )
    opensearch_client_.indices.refresh(index=SOURCE_INDEX_NAME)
    opensearch_client_.indices.refresh(index=DESTINATION_INDEX_NAME)

    # the source index has not been modified
    source_index = opensearch_client_.search(
        index=SOURCE_INDEX_NAME, size=3, body={"query": {"match_all": {}}}
    )
    assert len(source_index["hits"]["hits"]) == 3
    for hit in source_index["hits"]["hits"]:
        assert hit["_source"]["embedding"] == None

    # the destination index has been embedded
    destination_index = opensearch_client_.search(
        index=DESTINATION_INDEX_NAME, size=3, body={"query": {"match_all": {}}}
    )
    assert len(destination_index["hits"]["hits"]) == 3
    for hit in destination_index["hits"]["hits"]:
        assert (
            hit["_source"]["embedding"]
            == albert_embedding_response.response["data"][0]["embedding"]
        )
