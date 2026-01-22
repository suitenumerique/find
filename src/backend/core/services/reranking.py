"""Reranking utilities using rerankers library."""

import logging
from functools import cache

from django.conf import settings

from rerankers import Reranker  # pylint: disable=import-error
from rerankers.models.ranker import BaseRanker  # pylint: disable=import-error

from core.services.indexing import format_document
from core.utils import get_language_value

logger = logging.getLogger(__name__)


def rerank(query: str, hits: list[dict]) -> list[dict]:
    """
    Rerank search results using the configured reranker model.

    Args:
        query: The search query string
        hits: List of OpenSearch hit objects with _source containing title and content

    Returns:
        List of reranked results in the same format as input
    """

    reranker = get_reranker()
    if reranker is None:
        logger.warning("Could not import reranker, returning original results")
        return hits

    try:
        return _rerank(reranker, query, hits)

    except Exception as e:  # noqa: BLE001# pylint: disable=broad-exception-caught
        logger.error("Reranking failed: %s, returning original results", str(e))
        return hits


@cache
def get_reranker():
    """Get the reranker instance."""
    try:
        logger.info("Initializing reranker model: %s", settings.RERANKER_MODEL_NAME)
        reranker = Reranker(
            settings.RERANKER_MODEL_NAME, model_type=settings.RERANKER_MODEL_TYPE
        )
    except Exception as e:  # noqa: BLE001# pylint: disable=broad-exception-caught
        logger.error("Failed to initialize reranker: %s", str(e))
        return None

    logger.info("Reranker initialized successfully")
    return reranker


def _rerank(reranker: BaseRanker, query: str, original_hits: list[dict]):
    """Rerank the original results using the provided reranker."""
    documents = []
    doc_ids = []
    for hit in original_hits:
        title = get_language_value(hit["_source"], "title")
        content = get_language_value(hit["_source"], "content")
        documents.append(format_document(title, content))
        doc_ids = doc_ids.append(hit["_id"])

    logger.info("Reranking %d results for query: %s", len(original_hits), query)
    reranked = reranker.rank(query=query, docs=documents, doc_ids=doc_ids)

    print("reranked---", reranked.results)
    print("original_hits---", original_hits)
    reranked_results = []
    for reranked_result in reranked.results:
        hit = [hit for hit in original_hits if hit["_id"] == reranked_result.doc_id][0]
        hit["_reranked_score"] = reranked_result.score
        reranked_results.append(hit)

    logger.info("Reranking completed, returned %d results", len(reranked_results))

    return reranked_results
