"""
Test suite for reranking service
"""

from unittest.mock import MagicMock, patch

import pytest

from core.services.reranking import get_reranker, rerank

pytestmark = pytest.mark.django_db


@pytest.fixture
def mock_search_results():
    """Mock OpenSearch results for testing."""
    return [
        {
            "_id": "doc1",
            "_source": {
                "title": {"en": "python programming"},
                "content": {"en": "learn python basics"},
            },
            "_score": 1.5,
        },
        {
            "_id": "doc2",
            "_source": {
                "title": {"en": "java tutorial"},
                "content": {"en": "introduction to java"},
            },
            "_score": 1.2,
        },
        {
            "_id": "doc3",
            "_source": {
                "title": {"en": "web development"},
                "content": {"en": "html css javascript"},
            },
            "_score": 1.0,
        },
    ]


@pytest.fixture
def mock_reranker():
    """Mock reranker instance."""
    reranker = MagicMock()
    
    # Mock the rank method to return results in reversed order
    def mock_rank(query, docs):
        result = MagicMock()
        # Return documents in reversed order with mock scores
        result.results = [
            MagicMock(doc_id=len(docs) - 1 - i, score=0.9 - i * 0.1)
            for i in range(3)
        ]
        return result
    
    reranker.rank = mock_rank
    return reranker


@patch("core.services.reranking.settings")
def test_rerank_results_disabled(mock_settings, mock_search_results):
    """Test that reranking returns original results when disabled."""
    mock_settings.RERANKER_ENABLED = False
    
    result = rerank("test query", mock_search_results)
    
    assert result == mock_search_results
    assert len(result) == 3


@patch("core.services.reranking.settings")
@patch("core.services.reranking.get_reranker")
def test_rerank_results_enabled(
    mock_get_reranker, mock_settings, mock_search_results, mock_reranker
):
    """Test that reranking reorders results when enabled."""
    mock_settings.RERANKER_ENABLED = True
    mock_get_reranker.return_value = mock_reranker
    
    result = rerank("python tutorial", mock_search_results)
    
    # Results should be reordered (reversed in our mock)
    assert len(result) == 3
    assert result[0]["_id"] == "doc3"
    assert result[1]["_id"] == "doc2"
    assert result[2]["_id"] == "doc1"
    
    # Check rerank scores were added
    assert "_rerank_score" in result[0]
    assert result[0]["_rerank_score"] == 0.9


@patch("core.services.reranking.settings")
@patch("core.services.reranking.get_reranker")
def test_rerank_results_with_top_k(
    mock_get_reranker, mock_settings, mock_search_results, mock_reranker
):
    """Test that top_k limits results."""
    mock_settings.RERANKER_ENABLED = True
    mock_get_reranker.return_value = mock_reranker
    
    result = rerank("python tutorial", mock_search_results, top_k=2)
    
    assert len(result) == 2
    assert result[0]["_id"] == "doc3"
    assert result[1]["_id"] == "doc2"


@patch("core.services.reranking.settings")
@patch("core.services.reranking.get_reranker")
def test_rerank_results_empty_list(mock_get_reranker, mock_settings):
    """Test that empty results return empty list."""
    mock_settings.RERANKER_ENABLED = True
    
    result = rerank("test query", [])
    
    assert result == []


@patch("core.services.reranking.settings")
@patch("core.services.reranking.get_reranker")
def test_rerank_results_reranker_unavailable(
    mock_get_reranker, mock_settings, mock_search_results
):
    """Test fallback when reranker is unavailable."""
    mock_settings.RERANKER_ENABLED = True
    mock_get_reranker.return_value = None
    
    result = rerank("test query", mock_search_results)
    
    # Should return original results
    assert result == mock_search_results


@patch("core.services.reranking.settings")
@patch("core.services.reranking.get_reranker")
def test_rerank_results_exception_handling(
    mock_get_reranker, mock_settings, mock_search_results, mock_reranker
):
    """Test that exceptions during reranking are handled gracefully."""
    mock_settings.RERANKER_ENABLED = True
    mock_reranker.rank.side_effect = Exception("Reranking failed")
    mock_get_reranker.return_value = mock_reranker
    
    result = rerank("test query", mock_search_results)
    
    # Should return original results on exception
    assert result == mock_search_results


@patch("core.services.reranking.settings")
def test_rerank_results_with_simple_strings(mock_settings, mock_reranker):
    """Test reranking with simple string title/content (not multilingual)."""
    mock_settings.RERANKER_ENABLED = True
    
    results = [
        {
            "_id": "doc1",
            "_source": {
                "title": "simple title",
                "content": "simple content",
            },
            "_score": 1.0,
        }
    ]
    
    with patch("core.services.reranking.get_reranker", return_value=mock_reranker):
        result = rerank("query", results)
        
        assert len(result) == 1
        assert "_rerank_score" in result[0]


@patch("core.services.reranking.settings")
@patch("core.services.reranking.Reranker")
def test_get_reranker_initialization(mock_reranker_class, mock_settings):
    """Test reranker initialization."""
    mock_settings.RERANKER_ENABLED = True
    mock_settings.RERANKER_MODEL_NAME = "test-model"
    mock_settings.RERANKER_MODEL_TYPE = "flashrank"
    
    # Reset global state
    import core.services.reranking as reranking_module
    reranking_module._reranker_instance = None  # noqa: SLF001
    
    reranker = get_reranker()
    
    mock_reranker_class.assert_called_once_with(
        "test-model",
        model_type="flashrank",
    )
    assert reranker is not None


@patch("core.services.reranking.settings")
def test_get_reranker_import_error(mock_settings):
    """Test reranker when library is not installed."""
    mock_settings.RERANKER_ENABLED = True
    
    # Reset global state
    import core.services.reranking as reranking_module
    reranking_module._reranker_instance = None  # noqa: SLF001
    
    with patch("core.services.reranking.Reranker", side_effect=ImportError):
        reranker = get_reranker()
        
        assert reranker is None


@patch("core.services.reranking.settings")
def test_get_reranker_disabled(mock_settings):
    """Test that reranker is not initialized when disabled."""
    mock_settings.RERANKER_ENABLED = False
    
    # Reset global state
    import core.services.reranking as reranking_module
    reranking_module._reranker_instance = None  # noqa: SLF001
    
    reranker = get_reranker()
    
    assert reranker is None
