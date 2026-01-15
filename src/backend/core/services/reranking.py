"""Reranking utilities using rerankers library."""

import logging
from functools import cache
from rerankers import Reranker, Document

from django.conf import settings

from core.services.indexing import format_document
from core.utils import get_language_value

logger = logging.getLogger(__name__)


@cache
def get_reranker():
    """Get or create the reranker instance (singleton pattern for efficiency)."""
    try:
        logger.info("Initializing reranker model: %s", settings.RERANKER_MODEL_NAME)
        reranker = Reranker("mixedbread-ai/mxbai-rerank-large-v1", model_type="cross-encoder")
        logger.info("Reranker initialized successfully")
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to initialize reranker: %s", str(e))
        return None
    
    return reranker


def rerank(query, results):
    """
    Rerank search results using the configured reranker model.
    
    Args:
        query: The search query string
        results: List of OpenSearch hit objects with _source containing title and content

    Returns:
        List of reranked results in the same format as input
    """
    if not settings.RERANKER_ENABLED:
        logger.debug("Reranker disabled, returning original results")
        return results

    reranker = get_reranker()
    if reranker is None:
        logger.warning("Reranker not available, returning original results")
        return results
    
    try:
        documents = []
        for hit in results:
            title = get_language_value(hit["_source"], "title")
            content = get_language_value(hit["_source"], "content")
            documents.append(format_document(title, content))
        
        logger.info("Reranking %d results for query: %s", len(results), query)
        reranked = reranker.rank(query=query, docs=documents)
        
        reranked_results = []
        for reranked_result in reranked.results:
            # doc_id is the index position in the original list
            original_hit = results[reranked_result.doc_id]
            # Add reranking score as metadata
            original_hit["_rerank_score"] = reranked_result.score
            reranked_results.append(original_hit)
        
        logger.info("Reranking completed, returned %d results", len(reranked_results))

        return reranked_results
        
    except Exception as e:  # noqa: BLE001
        logger.error("Reranking failed: %s, returning original results", str(e))
        return results
