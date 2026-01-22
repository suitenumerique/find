"""
Test suite for reranking service
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from core.services.reranking import rerank

pytestmark = pytest.mark.django_db

logger = logging.getLogger(__name__)


@pytest.fixture
def original_hits():
    """Sample OpenSearch hits for testing"""
    return [
        {
            "_id": "1",
            "_score": 1.5,
            "_source": {
                "title.en": "Dogs and wolves",
                "content.en": "Dogs are domesticated wolves",
            },
        },
        {
            "_id": "2",
            "_score": 1.2,
            "_source": {
                "title.en": "Cats as pets",
                "content.en": "Cats are popular pets",
            },
        },
        {
            "_id": "3",
            "_score": 1.0,
            "_source": {
                "title.en": "Birds in nature",
                "content.en": "Birds fly in the sky",
            },
        },
    ]


@pytest.fixture
def mock_reranker_result():
    """Mock reranker result with reranked scores"""
    result = MagicMock()
    result.results = [
        MagicMock(doc_id=1, score=0.95),
        MagicMock(doc_id=0, score=0.87),
        MagicMock(doc_id=2, score=0.45),
    ]
    return result


@patch("core.services.reranking.get_reranker")
def test_return_original_results_if_reranker_import_fails(
    mock_get_reranker, original_hits, caplog
):
    """Test that original results are returned if reranker import fails"""
    mock_get_reranker.return_value = None

    with caplog.at_level(logging.WARNING):
        result = rerank("test query", original_hits)

    assert result == original_hits
    assert any(
        "Could not import reranker, returning original results" in message
        for message in caplog.messages
    )


@patch("core.services.reranking.get_reranker")
def test_return_original_results_if_reranking_fails(
    mock_get_reranker, original_hits, caplog
):
    """Test that original results are returned if reranking fails"""
    mock_reranker = MagicMock()
    mock_reranker.rank.side_effect = Exception("Reranking service error")
    mock_get_reranker.return_value = mock_reranker

    with caplog.at_level(logging.ERROR):
        result = rerank("test query", original_hits)

    assert result == original_hits
    assert any(
        "Reranking failed: Reranking service error, returning original results"
        in message
        for message in caplog.messages
    )


@patch("core.services.reranking.get_reranker")
def test_reranking_success(
    mock_get_reranker, original_hits, mock_reranker_result, caplog
):
    """Test successful reranking of search results"""
    mock_reranker = MagicMock()
    mock_reranker.rank.return_value = mock_reranker_result
    mock_get_reranker.return_value = mock_reranker

    with caplog.at_level(logging.INFO):
        result = rerank("test query", original_hits)

    assert len(result) == 3
    assert result[0]["_id"] == "2"
    assert result[0]["_reranked_score"] == 0.95
    assert result[1]["_id"] == "1"
    assert result[1]["_reranked_score"] == 0.87
    assert result[2]["_id"] == "3"
    assert result[2]["_reranked_score"] == 0.45

    mock_reranker.rank.assert_called_once()
    call_args = mock_reranker.rank.call_args
    assert call_args.kwargs["query"] == "test query"
    assert len(call_args.kwargs["docs"]) == 3

    assert any(
        "Reranking 3 results for query: test query" in message
        for message in caplog.messages
    )
    assert any(
        "Reranking completed, returned 3 results" in message
        for message in caplog.messages
    )
