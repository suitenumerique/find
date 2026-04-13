"""Celery tasks for document indexing."""

import logging

from core.enums import IndexingStatusEnum
from core.services.opensearch import check_hybrid_search_enabled
from core.services.reindex import reindex_with_embedding

from find.celery_app import app

logger = logging.getLogger(__name__)


@app.task()
def embed_document_to_be_embedded(index_name: str):
    """
    Asynchronous task to embed all documents with status 'to-be-embedded'.

    Args:
        index_name: Name of the service whose documents need embedding
    """
    if not check_hybrid_search_enabled():
        logger.warning(
            "Hybrid search is not enabled for index %s. Embedding task will not run.",
            index_name,
        )
        return

    result = reindex_with_embedding(
        index_name,
        {
            "bool": {
                "must": [
                    {"term": {"indexing_status": IndexingStatusEnum.TO_BE_EMBEDDED}}
                ]
            }
        },
    )

    logger.info(
        "[INFO] Indexing of %s is done.\n"
        "nb success embedding: %s\n"
        "nb failed embedding: %s embedding fails\n",
        index_name,
        result["nb_success_embedding"],
        result["nb_failed_embedding"],
    )
