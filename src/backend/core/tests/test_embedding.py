"""
Test suite for opensearch embedding service
"""

import logging
from json import dumps as json_dumps

import pytest
import responses

from core.services.embedding import embed_text
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client

from ..services.indexing import chunk_document
from .mock import albert_embedding_response
from .utils import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_utils,
)
from .utils import (
    enable_hybrid_search,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def before_each():
    """Clear caches before each test"""
    clear_caches()
    yield
    clear_caches()


def clear_caches():
    """Clear caches used in opensearch service and factories"""
    check_hybrid_search_enabled.cache_clear()
    # the instance of check_hybrid_search_enabled used in utils.py
    # is different and must be cleared separately
    check_hybrid_search_enabled_utils.cache_clear()
    opensearch_client().indices.delete(index="*")


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


@responses.activate
def test_chunk_document_success(settings):
    """Test that chunk_document correctly chunks and embeds document content"""

    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    title = "Test Document"
    content = "a long text to embed. " * 100  # Create content long enough for chunking

    chunks = chunk_document(title, content)

    # Verify chunks were created
    assert chunks is not None
    assert len(chunks) > 1  # Should be split into multiple chunks

    # Verify chunk structure
    expected_num_chunks = (
        int(len(content) / (settings.CHUNK_SIZE - settings.CHUNK_OVERLAP)) + 1
    )
    assert len(chunks) == expected_num_chunks

    # Verify each chunk has correct structure and data
    for idx, chunk in enumerate(chunks):
        assert chunk["index"] == idx
        assert "content" in chunk
        assert "embedding" in chunk
        assert chunk["content"] in content
        assert len(chunk["content"]) < len(content)
        assert (
            chunk["embedding"]
            == albert_embedding_response.response["data"][0]["embedding"]
        )


@responses.activate
def test_chunk_document_embedding_failure(settings, caplog):
    """Test that chunk_document returns None if any embedding fails"""

    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        status=500,
        body=json_dumps({"message": "Internal server error."}),
    )

    title = "Test Document"
    content = "a long text to embed. " * 100

    with caplog.at_level(logging.WARNING):
        chunks = chunk_document(title, content)

    # Should return None if embedding fails
    assert chunks is None
    assert any("Failed to embed chunk" in message for message in caplog.messages)
