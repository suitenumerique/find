"""Reranking utilities using rerankers library."""

import logging
from functools import cache
from rerankers import Reranker, Document

from django.conf import settings
from rerankers.models.ranker import BaseRanker

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
    if not settings.RERANKER_ENABLED:
        logger.debug("Reranker disabled, returning original results")
        return hits

    reranker = get_reranker()
    if reranker is None:
        logger.warning("Reranker not available, returning original results")
        return hits

    try:
        return _rerank(reranker, query, hits)

    except Exception as e:  # noqa: BLE001
        logger.error("Reranking failed: %s, returning original results", str(e))
        return hits


@cache
def get_reranker():
    """Get the reranker instance."""
    try:
        logger.info("Initializing reranker model: %s", settings.RERANKER_MODEL_NAME)
        reranker = Reranker(settings.RERANKER_MODEL_NAME, model_type=settings.RERANKER_MODEL_TYPE)
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to initialize reranker: %s", str(e))
        return None

    logger.info("Reranker initialized successfully")
    return reranker


def _rerank(reranker: BaseRanker, query: str, original_hits: list[dict]):
    """Rerank the original results using the provided reranker."""
    documents = []
    for hit in original_hits:
        title = get_language_value(hit["_source"], "title")
        content = get_language_value(hit["_source"], "content")
        documents.append(format_document(title, content))

    logger.info("Reranking %d results for query: %s", len(original_hits), query)
    reranked = reranker.rank(query=query, docs=documents)

    reranked_results = []
    for reranked_result in reranked.results:
        hit = original_hits[reranked_result.doc_id]
        hit["_reranked_score"] = reranked_result.score
        reranked_results.append(hit)

    logger.info("Reranking completed, returned %d results", len(reranked_results))

    return reranked_results
