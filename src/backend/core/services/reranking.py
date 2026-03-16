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
        List of reranked results in the same format as input with a _reranked_score
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
def get_reranker() -> BaseRanker | None:
    """
    Get the reranker instance.
    Returns None if the reranker library is not available or if initialization fails but
    does not raise an exception to avoid crashing the application.
    """
    try:
        logger.info("Initializing reranker model: %s", settings.RERANKER_MODEL_NAME)
        return Reranker(
            settings.RERANKER_MODEL_NAME,
            model_type=settings.RERANKER_MODEL_TYPE,
            api_key=settings.RERANKER_API_KEY,
        )
    except Exception as e:  # noqa: BLE001# pylint: disable=broad-exception-caught
        logger.error("Failed to initialize reranker: %s", str(e))
        return None


def _rerank(reranker: BaseRanker, query: str, original_hits: list[dict]) -> list[dict]:
    """Rerank the original results using the provided reranker."""
    docs, doc_ids = prepare_rerank_data(original_hits)

    logger.info("Reranking %d results for query: %s", len(original_hits), query)
    reranked = reranker.rank(query=query, docs=docs, doc_ids=doc_ids)

    reranked_results: list[dict] = []
    for reranked_result in reranked.results:
        matching_hits = [
            hit for hit in original_hits if hit["_id"] == reranked_result.doc_id
        ]

        if not matching_hits:
            logger.warning(
                "Reranked document ID %s not found in original hits, skipping",
                reranked_result.doc_id,
            )
            continue

        if len(matching_hits) > 1:
            logger.warning(
                "Multiple hits found for document ID %s, using first match",
                reranked_result.doc_id,
            )

        hit = matching_hits[0]
        hit["_reranked_score"] = reranked_result.score
        reranked_results.append(hit)

    logger.info("Reranking completed, returned %d results", len(reranked_results))

    return reranked_results


def prepare_rerank_data(original_hits: list[dict]) -> tuple[list[str], list[str]]:
    """
    Prepare the documents for reranking by extracting the title and content from the original hits.
    """
    docs = []
    doc_ids = []
    for hit in original_hits:
        title = get_language_value(hit["_source"], "title")
        content = get_language_value(hit["_source"], "content")

        docs.append(format_document(title, content))
        doc_ids.append(hit["_id"])

    return docs, doc_ids


def should_rerank(is_rerank_requested: bool | None) -> bool:
    """
    Determine whether to perform reranking based on the input parameter and settings.
    logs warning if reranking was explicitly requested but the reranker is disabled in settings.
    falls back to settings.RERANKER_ENABLED if is_rerank_requested is None.
    """
    if is_rerank_requested and not settings.RERANKER_ENABLED:
        logger.warning(
            "Reranking was explicitly requested but the reranker "
            "is disabled in settings. Reranking skipped."
        )
        return False

    if is_rerank_requested is None:
        return settings.RERANKER_ENABLED

    return is_rerank_requested and settings.RERANKER_ENABLED
