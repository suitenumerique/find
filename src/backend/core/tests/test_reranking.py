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
        "_id": "doc-1",
        "_score": 1.5,
        "_source": {
            "title.en": "Dogs and wolves",
            "content.en": "Dogs are domesticated wolves",
        },
    },
    {
        "_id": "doc-2",
        "_score": 1.2,
        "_source": {
            "title.en": "Cats as pets",
            "content.en": "Cats are popular pets",
        },
    },
    {
        "_id": "doc-3",
        "_score": 1.0,
        "_source": {
            "title.en": "Birds in nature",
            "content.en": "Birds fly in the sky",
        },
    },
]

RERANKER_RESULTS = [
    {"doc_id": "doc-2", "score": 0.95},
    {"doc_id": "doc-1", "score": 0.87},
    {"doc_id": "doc-3", "score": 0.45},
]


@pytest.fixture(name="get_reranker")
def mock_get_reranker():
    """Mock reranker result with reranked scores"""
    with patch("core.services.reranking.get_reranker") as mocked_get_reranker:
        reranker_result = MagicMock()

        reranker_result.results = [
            MagicMock(**reranker_result) for reranker_result in RERANKER_RESULTS
        ]

        mock_reranker = MagicMock()
        mock_reranker.rank.return_value = reranker_result
        mocked_get_reranker.return_value = mock_reranker

        # Yield both the patched function and the mock reranker instance
        yield mock_reranker


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
    mock_reranker.rank.side_effect = Exception("Reranking service error")
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


def test_reranking_success(get_reranker, caplog):
    """Test successful reranking of search results"""
    mock_reranker = get_reranker

    q = "test query"
    with caplog.at_level(logging.INFO):
        reranked_hits = rerank(q, ORIGINAL_HITS.copy())

    assert any(
        f"Reranking 3 results for query: {q}" in message for message in caplog.messages
    )
    assert any(
        "Reranking completed, returned 3 results" in message
        for message in caplog.messages
    )

    mock_reranker.rank.assert_called_once()
    call_args = mock_reranker.rank.call_args
    assert call_args.kwargs["query"] == q
    assert len(call_args.kwargs["docs"]) == len(RERANKER_RESULTS)

    for ranked_hit_index, ranked_hit in enumerate(reranked_hits):
        reranker_result = RERANKER_RESULTS[ranked_hit_index]
        expected_doc_id = reranker_result["doc_id"]
        expected_score = reranker_result["score"]
        expected_reranked_hit = ORIGINAL_HITS[
            next(
                _hit_index
                for _hit_index, hit in enumerate(ORIGINAL_HITS)
                if hit["_id"] == expected_doc_id
            )
        ]

        assert expected_doc_id == ranked_hit["_id"]
        assert expected_reranked_hit["_id"] == ranked_hit["_id"]
        assert expected_reranked_hit["_source"] == ranked_hit["_source"]
        assert expected_reranked_hit["_score"] == ranked_hit["_score"]
        assert expected_score == expected_reranked_hit["_reranked_score"]
