"""Command Service model for find's core app."""

import logging
from typing import List

from django.conf import settings as django_settings

from opensearchpy.exceptions import NotFoundError

from core import factories
from core.services import opensearch
from core.services.opensearch import (
    prepare_document_for_indexing,
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


def prepare_index(
    index_name, documents: List, language_code=django_settings.DEFAULT_LANGUAGE_CODE
):
    """Prepare the search index."""
    logger.info(f"prepare_index {index_name} with {len(documents)} documents")
    opensearch_client_ = opensearch.opensearch_client()

    actions = []
    for document in documents:
        document_dict = prepare_document_for_indexing(
            document, language_code=language_code
        )
        _id = document_dict.pop("id")
        actions.append({"index": {"_id": _id}})
        actions.append(document_dict)

    opensearch_client_.bulk(index=index_name, body=actions)
    count = opensearch_client_.count(index=index_name)["count"]
    if count != len(documents):
        raise ValueError(
            f"Indexing error: expected {len(documents)} documents, but found {count} in index {index_name}"
        )
