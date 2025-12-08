"""
Test suite for evaluate_search_engine management command
"""

import io
import logging
from unittest.mock import patch

from django.core.management import call_command

import pytest
import responses

from core.services.opensearch import check_hybrid_search_enabled, opensearch_client
from core.tests.mock import albert_embedding_response
from core.utils import delete_index, delete_search_pipeline

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.django_db


INDEX_NAME = "evaluation-index"


@pytest.fixture(autouse=True)
def clear_caches_and_cleanup():
    """Clear caches and cleanup before and after each test"""
    clear()
    yield
    clear()


def clear():
    check_hybrid_search_enabled.cache_clear()
    delete_search_pipeline()
    delete_index(INDEX_NAME)


@pytest.fixture
def mock_embedding_api(settings):
    """Mock the embedding API for tests"""
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )


def assert_output_successful(output):
    assert "[INFO] Starting evaluation with 1 documents and 1 queries" in output
    assert "[QUERY EVALUATION]" in output
    assert "q: a query" in output
    assert "[SUMMARY] Average Performance" in output
    assert "Average NDCG:" in output
    assert "Average Precision:" in output
    assert "Average Recall:" in output
    assert "Average F1-Score:" in output
    assert "[SUCCESS] Evaluation completed" in output


@responses.activate
def test_evaluate_search_engine_command_v0(settings, mock_embedding_api):
    """Test running the evaluate_search_engine command with v0 dataset"""
    out = io.StringIO()

    call_command(
        "evaluate_search_engine",
        "v0",
        stdout=out,
    )

    assert_output_successful(out.getvalue())

    # Index should still exist because keep-index is True by default
    assert opensearch_client().indices.exists(index="evaluation-index")


@responses.activate
def test_evaluate_search_engine_command_without_keep_index(mock_embedding_api):
    """Test that keep-index option False erases index"""
    out = io.StringIO()

    call_command(
        "evaluate_search_engine",
        "v0",
        keep_index=False,
        stdout=out,
    )

    assert_output_successful(out.getvalue())

    # Index should not exist
    assert not opensearch_client().indices.exists(index="evaluation-index")


@patch("evaluation.management.commands.evaluate_search_engine.delete_index")
@responses.activate
def test_evaluate_search_engine_command_force_reindex(
    mock_delete_index, mock_embedding_api
):
    """Test that force-reindex must delete and recreates the index"""
    out = io.StringIO()

    # run once to create the index
    call_command(
        "evaluate_search_engine",
        "v0",
        stdout=out,
    )

    mock_delete_index.clear()
    # Run again with force-reindex
    call_command(
        "evaluate_search_engine",
        "v0",
        force_reindex=True,
        stdout=out,
    )

    # Verify delete_index was called once with the correct index name
    mock_delete_index.assert_called_once_with("evaluation-index")


@responses.activate
def test_evaluate_search_engine_min_score_filter(settings, mock_embedding_api):
    """Test that min_score filters out low-scoring results"""

    out = io.StringIO()
    super_hight_score = 1000.0
    call_command(
        "evaluate_search_engine",
        "v0",
        min_score=super_hight_score,
        stdout=out,
    )

    # Assert all scores are null proving all results were filtered out
    assert (
        "NDCG: 0.00% \n  PRECISION: 0.00% \n  RECALL: 0.00% \n  F1-SCORE: 0.00%"
        in out.getvalue()
    )
