"""
Test suite for opensearch service
"""

import logging
import operator
from json import dumps as json_dumps

import pytest
import responses
from opensearchpy.exceptions import NotFoundError

from core.services import opensearch

from ..services.opensearch import (
    HYBRID_SEARCH_PIPELINE_ID,
    check_hybrid_search_enabled,
    embed_text,
    search,
)
from .mock import albert_embedding_response
from .utils import (
    bulk_create_documents,
    delete_search_pipeline,
    prepare_index,
)

pytestmark = pytest.mark.django_db


SERVICE_NAME = "test-service"
PARAMS = {
    "page_number": 1,
    "page_size": 20,
    "k": 20,
    "order_by": "relevance",
    "order_direction": "desc",
    "search_indices": {SERVICE_NAME},
    "reach": None,
    "user_sub": "user_sub",
    "groups": [],
    "visited": [],
}


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear caches and delete search pipeline before each test"""
    check_hybrid_search_enabled.cache_clear()
    delete_search_pipeline()


@responses.activate
def test_hybrid_search_success(settings, caplog):
    """Test the hybrid search is successful"""
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
    prepare_index(SERVICE_NAME, documents)

    with caplog.at_level(logging.INFO):
        result = search(q=q, **PARAMS)

    assert any(
        f"Performing hybrid search with embedding: {q}" in message
        for message in caplog.messages
    )
    assert any(
        f"Creating search pipeline: {HYBRID_SEARCH_PIPELINE_ID}" in message
        for message in caplog.messages
    )

    assert result["hits"]["max_score"] > 0.0
    # hybrid search always returns a response of fixed sized sorted and scored by relevance
    assert {hit["_source"]["title"] for hit in result["hits"]["hits"]} == {
        doc["title"] for doc in documents
    }


def test_fall_back_on_full_text_search_if_hybrid_search_disabled(settings, caplog):
    """Test the full-text search is done when HYBRID_SEARCH_ENABLED=Flase"""
    settings.HYBRID_SEARCH_ENABLED = False

    documents = bulk_create_documents(
        [
            {"title": "wolf", "content": "wolves live in packs and hunt together"},
            {"title": "dog", "content": "dogs are loyal domestic animals"},
            {"title": "cat", "content": "cats are curious and independent pets"},
        ]
    )
    q = "wolf"
    prepare_index(SERVICE_NAME, documents)

    with caplog.at_level(logging.INFO):
        result = search(q=q, **PARAMS)

    assert any(
        "Hybrid search is disabled via HYBRID_SEARCH_ENABLED setting" in message
        for message in caplog.messages
    )
    assert any(
        f"Performing full-text search without embedding: {q}" in message
        for message in caplog.messages
    )
    assert not any(
        f"Creating search pipeline: {HYBRID_SEARCH_PIPELINE_ID}" in message
        for message in caplog.messages
    )

    with pytest.raises(NotFoundError):
        #  assert that the hybrid search pipeline was not recreated
        opensearch.opensearch_client().transport.perform_request(
            method="GET",
            url=f"/_search/pipeline/{opensearch.HYBRID_SEARCH_PIPELINE_ID}",
        )
    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 1
    assert result["hits"]["hits"][0]["_source"]["title"] == "wolf"


@responses.activate
def test_fall_back_on_full_text_search_if_embedding_api_fails(settings, caplog):
    """Test the full-text search is done when the embedding api fails"""
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
    q = "wolf"
    prepare_index(SERVICE_NAME, documents)

    with caplog.at_level(logging.INFO):
        result = search(q=q, **PARAMS)

    assert any(
        "embedding API request failed: 401 Client Error: Unauthorized" in message
        for message in caplog.messages
    )
    assert any(
        f"Performing full-text search without embedding: {q}" in message
        for message in caplog.messages
    )
    assert not any(
        f"Creating search pipeline: {HYBRID_SEARCH_PIPELINE_ID}" in message
        for message in caplog.messages
    )

    with pytest.raises(NotFoundError):
        #  assert that the hybrid search pipeline was not recreated
        opensearch.opensearch_client().transport.perform_request(
            method="GET",
            url=f"/_search/pipeline/{opensearch.HYBRID_SEARCH_PIPELINE_ID}",
        )
    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 1
    assert result["hits"]["hits"][0]["_source"]["title"] == "wolf"


@responses.activate
def test_fall_back_on_full_text_search_if_variable_are_missing(settings, caplog):
    """Test the full-text search is done when variables are missing for hybrid search"""
    del settings.HYBRID_SEARCH_WEIGHTS
    responses.add(
        # mocking embedding api should not be necessary
        # weirdly enough the cache of check_hybrid_search_enabled seems not be cleared properly
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
    q = "wolf"
    prepare_index(SERVICE_NAME, documents)

    with caplog.at_level(logging.INFO):
        result = search(q=q, **PARAMS)

    assert any(
        "Missing variables for hybrid search: HYBRID_SEARCH_WEIGHTS" in message
        for message in caplog.messages
    )
    assert any(
        f"Performing full-text search without embedding: {q}" in message
        for message in caplog.messages
    )
    assert not any(
        f"Creating search pipeline: {HYBRID_SEARCH_PIPELINE_ID}" in message
        for message in caplog.messages
    )

    with pytest.raises(NotFoundError):
        #  assert that the hybrid search pipeline was not recreated
        opensearch.opensearch_client().transport.perform_request(
            method="GET",
            url=f"/_search/pipeline/{opensearch.HYBRID_SEARCH_PIPELINE_ID}",
        )
    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 1
    assert result["hits"]["hits"][0]["_source"]["title"] == "wolf"


@responses.activate
def test_match_all(settings, caplog):
    """Test match all when q='*' and no semantic search is needed"""
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
    q = "*"
    prepare_index(SERVICE_NAME, documents)

    with caplog.at_level(logging.INFO):
        result = search(q=q, **PARAMS)

    assert any("Performing match_all query" in message for message in caplog.messages)
    assert not any(
        f"Creating search pipeline: {HYBRID_SEARCH_PIPELINE_ID}" in message
        for message in caplog.messages
    )

    with pytest.raises(NotFoundError):
        #  assert that the hybrid search pipeline was not recreated
        opensearch.opensearch_client().transport.perform_request(
            method="GET",
            url=f"/_search/pipeline/{opensearch.HYBRID_SEARCH_PIPELINE_ID}",
        )
    assert result["hits"]["max_score"] > 0.0
    assert len(result["hits"]["hits"]) == 3


@responses.activate
def test_search_ordering_by_relevance(settings, caplog):
    """Test the hybrid supports ordering by relevance asc and desc"""
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
    prepare_index(SERVICE_NAME, documents)

    for direction in ["asc", "desc"]:
        with caplog.at_level(logging.INFO):
            result = search(q=q, **{**PARAMS, "order_direction": direction})

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
    prepare_index(SERVICE_NAME, documents)

    q = "pony"  # full-text matches 0 document
    for k in [1, 2, 3]:  # semantic should match k documents
        result = search(q=q, **{**PARAMS, "k": k})
        assert len(result["hits"]["hits"]) == k


@responses.activate
def test_embed_text_success(settings):
    """Test embed_text retrieval is successful"""
    text = "canine pet"
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    embedding = embed_text(text)

    assert embedding == albert_embedding_response.response["data"][0]["embedding"]


@responses.activate
def test_embed_401_http_error(settings, caplog):
    """Test embed_text does not crash and returns None on 401 error"""
    text = "canine pet"
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        status=401,
        body=json_dumps({"message": "Authentication failed."}),
    )

    with caplog.at_level(logging.WARNING):
        embedding = embed_text(text)

    assert any(
        "embedding API request failed: 401 Client Error: Unauthorized" in message
        for message in caplog.messages
    )

    assert embedding is None


@responses.activate
def test_embed_500_http_error(settings, caplog):
    """Test embed_text does not crash and returns None on 500 error"""
    text = "canine pet"
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        status=500,
        body=json_dumps({"message": "Internal server error."}),
    )

    with caplog.at_level(logging.WARNING):
        embedding = embed_text(text)

    assert any(
        "embedding API request failed: 500 Server Error: Internal Server Error"
        in message
        for message in caplog.messages
    )

    assert embedding is None


@responses.activate
def test_embed_wrong_format(settings, caplog):
    """Test embed_text does not crash and returns None if api returns a wrong format"""
    text = "canine pet"
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json={"wrong": "format"},
        status=200,
    )

    with caplog.at_level(logging.WARNING):
        embedding = embed_text(text)

    assert any(
        "unexpected embedding response format" in message for message in caplog.messages
    )

    assert embedding is None
