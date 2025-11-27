"""Tests Service model for find's core app."""

import logging
from typing import List

from django.conf import settings as django_settings

from opensearchpy.exceptions import NotFoundError

from core import factories
from core.services import opensearch
from core.services.opensearch import (
    check_hybrid_search_enabled,
    embed_text,
    format_document,
)

logger = logging.getLogger(__name__)


def bulk_create_documents(document_payloads):
    """Create documents in bulk from payloads"""
    return [
        factories.DocumentSchemaFactory.build(**document_payload, users=["user_sub"])
        for document_payload in document_payloads
    ]


def delete_search_pipeline():
    """Delete the hybrid search pipeline if it exists"""
    logger.info(f"Deleting search pipeline {django_settings.HYBRID_SEARCH_PIPELINE_ID}")

    try:
        opensearch.opensearch_client().transport.perform_request(
            method="DELETE",
            url=f"/_search/pipeline/{django_settings.HYBRID_SEARCH_PIPELINE_ID}",
        )
    except NotFoundError:
        logger.info("Search pipeline not found, nothing to delete.")


def delete_index(index_name):
    """Delete the hybrid search pipeline if it exists"""
    logger.info(f"Deleting Index {index_name}")

    try:
        opensearch.opensearch_client().indices.delete(index=index_name)
    except NotFoundError:
        logger.info("Search pipeline %s not found, nothing to delete.", index_name)


def prepare_index(index_name, documents: List):
    """Prepare the search index."""
    logger.info(f"prepare_index {index_name} with {len(documents)} documents")
    opensearch_client_ = opensearch.opensearch_client()
    opensearch.ensure_index_exists(index_name)
    actions = []
    for document in documents:
        document_dict = {
            **document,
            "embedding": embed_text(
                format_document(document["title"], document["content"])
            )
            if check_hybrid_search_enabled()
            else None,
            "embedding_model": django_settings.EMBEDDING_API_MODEL_NAME
            if check_hybrid_search_enabled()
            else None,
        }
        _id = document_dict.pop("id")
        actions.append({"index": {"_id": _id}})
        actions.append(document_dict)

    opensearch_client_.bulk(index=index_name, body=actions)
    opensearch_client_.indices.refresh(index=index_name)
    count = opensearch_client_.count(index=index_name)["count"]
    if count != len(documents):
        raise ValueError(
            f"Indexing error: expected {len(documents)} documents, but found {count} in index {index_name}"
        )
