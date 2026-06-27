"""Tests Service model for find's core app."""

import logging
from typing import List

from django.conf import settings as django_settings

from opensearchpy.helpers import bulk

from core.services.indexing import ensure_index_exists, prepare_document_for_indexing
from core.services.opensearch import opensearch_client

logger = logging.getLogger(__name__)


def prepare_index(index_name, documents: List):
    """Prepare the search index before testing a query on it."""
    logger.info("Preparing index %s with %d documents", index_name, len(documents))

    ensure_index_exists(index_name)
    actions = [
        {
            "_op_type": "index",
            "_index": index_name,
            "_id": document["id"],
            "_source": prepare_document_for_indexing(document),
        }
        for document in documents
    ]
    bulk(opensearch_client(), actions)
    opensearch_client().indices.refresh(index=index_name)


def get_language_value(source, language_field):
    """
    extract the value of the language field with the correct language_code extension.
    "title" and "content" have extensions like "title.en" or "title.fr".
    get_language_value will return the value regardless of the extension.
    """
    for language_code in django_settings.SUPPORTED_LANGUAGE_CODES:
        if f"{language_field}.{language_code}" in source:
            return source[f"{language_field}.{language_code}"]
    raise ValueError(
        f"No '{language_field}' field with any supported language code in object"
    )
