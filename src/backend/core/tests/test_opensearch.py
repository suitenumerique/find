"""
Test suite for opensearch service
"""

import logging
import operator
from json import dumps as json_dumps

import pytest
import responses

from core import factories
from core.services import opensearch
from core.services.opensearch import (
    check_hybrid_search_enabled,
    embed_text,
    ensure_index_exists,
    opensearch_client,
    search,
)

from .mock import albert_embedding_response
from .utils import (
    bulk_create_documents,
    delete_search_pipeline,
    enable_hybrid_search,
    prepare_index,
)
from .utils import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_utils,
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
    assert {hit["_source"]["title"] for hit in result["hits"]["hits"]} == {
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
    assert indexed_documents["hits"]["hits"][0]["_source"]["embedding"] is None

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
    assert result["hits"]["hits"][0]["_source"]["title"] == q


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
    assert result["hits"]["hits"][0]["_source"]["title"] == "wolf"


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
    assert result["hits"]["hits"][0]["_source"]["title"] == "wolf"


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
    assert result["hits"]["hits"][0]["_source"]["title"] == "wolf"


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


@responses.activate
def test_embed_text_success(settings):
    """Test embed_text retrieval is successful"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )
    text = "canine pet"

    embedding = embed_text(text)

    assert embedding == albert_embedding_response.response["data"][0]["embedding"]


@responses.activate
def test_embed_401_http_error(settings, caplog):
    """Test embed_text does not crash and returns None on 401 error"""
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        status=401,
        body=json_dumps({"message": "Authentication failed."}),
    )
    text = "canine pet"

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
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        status=500,
        body=json_dumps({"message": "Internal server error."}),
    )
    text = "canine pet"

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
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json={"wrong": "format"},
        status=200,
    )
    text = "canine pet"

    with caplog.at_level(logging.WARNING):
        embedding = embed_text(text)

    assert any(
        "unexpected embedding response format" in message for message in caplog.messages
    )

    assert embedding is None


def test_opensearch_analyzer(settings):
    """Test the french_analyzer is correctly configured in OpenSearch"""
    enable_hybrid_search(settings)
    ensure_index_exists(SERVICE_NAME)

    text = "l'éléphant a couru avec les Gens"

    french_analyzer_response = opensearch_client().indices.analyze(
        index=SERVICE_NAME,
        body={
            "analyzer": "french_analyzer",
            "text": text,
        },
    )
    french_analyzer_tokens = [
        token_info["token"] for token_info in french_analyzer_response["tokens"]
    ]
    response_trigram_analyzer = opensearch_client().indices.analyze(
        index=SERVICE_NAME,
        body={
            "analyzer": "trigram_analyzer",
            "text": text,
        },
    )
    trigram_analyzer_tokens = [
        token_info["token"] for token_info in response_trigram_analyzer["tokens"]
    ]

    # lowercase is applied ("Gens" -> "gens")
    # asciifolding is applied ("éléphant" -> "elephant")
    # stop words are removed ('avec', 'les')
    # elisions are removed ("l'")
    # stemming is applied ("gens" -> "gen")
    assert french_analyzer_tokens == ["elephant", "a", "couru", "gen"]

    # lowercase is applied ("Gens" -> "gens")
    # asciifolding is applied ("éléphant" -> "elephant")
    # trigrams are generated
    assert trigram_analyzer_tokens == [
        "l'e",
        "'el",
        "ele",
        "lep",
        "eph",
        "pha",
        "han",
        "ant",
        "cou",
        "our",
        "uru",
        "ave",
        "vec",
        "les",
        "gen",
        "ens",
    ]
