"""
Test suite for reranking service
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from core.services.reranking import rerank

pytestmark = pytest.mark.django_db

logger = logging.getLogger(__name__)


ORIGINAL_HITS = [
    {
        "_id": "doc-0",
        "_score": 1.5,
        "_source": {
            "title.en": "Dogs",
            "content.en": "Dogs are domesticated wolves",
        },
    },
    {
        "_id": "doc-1",
        "_score": 1.2,
        "_source": {
            "title.en": "Cats",
            "content.en": "Cats are popular pets",
        },
    },
    {
        "_id": "doc-2",
        "_score": 1.0,
        "_source": {
            "title.en": "Birds",
            "content.en": "Birds fly in the sky",
        },
    },
]


@patch("core.services.reranking.get_reranker")
def test_return_original_results_if_reranker_import_fails(mocked_get_reranker, caplog):
    """Test that original results are returned if reranker import fails"""
    mocked_get_reranker.return_value = None

    with caplog.at_level(logging.WARNING):
        result = rerank("test query", ORIGINAL_HITS)

    assert result == ORIGINAL_HITS
    assert any(
        "Could not import reranker, returning original results" in message
        for message in caplog.messages
    )


@patch("core.services.reranking.get_reranker")
def test_return_original_results_if_reranking_fails(mocked_get_reranker, caplog):
    """Test that original results are returned if reranking fails"""
    mock_reranker = MagicMock()
    mock_reranker.rerank.side_effect = Exception("Reranking service error")
    mocked_get_reranker.return_value = mock_reranker

    q = "test query"
    with caplog.at_level(logging.ERROR):
        result = rerank(q, ORIGINAL_HITS)

    assert result == ORIGINAL_HITS
    assert any(
        "Reranking failed: Reranking service error, returning original results"
        in message
        for message in caplog.messages
    )


def test_reranking_success(caplog, settings):
    """Test successful reranking of search results"""
    settings.RERANKER_MODEL_NAME = "ms-marco-MiniLM-L-12-v2"

    q = "cats"
    with caplog.at_level(logging.INFO):
        reranked_hits = rerank(q, ORIGINAL_HITS.copy())

    assert any(
        f"Reranking 3 results for query: {q}" in message for message in caplog.messages
    )
    assert any(
        "Reranking completed, returned 3 results" in message
        for message in caplog.messages
    )

    # if the reranking is not too bad it should definitely rerank doc-1 at top position
    assert reranked_hits[0]["_id"] == ORIGINAL_HITS[1]["_id"]
    # reranked_hits should be sorted by _reranked_score
    assert reranked_hits[0]["_reranked_score"] > reranked_hits[1]["_reranked_score"]
    assert reranked_hits[1]["_reranked_score"] > reranked_hits[2]["_reranked_score"]
