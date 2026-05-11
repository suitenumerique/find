"""Tests Service model for find's core app."""

import logging

from django.conf import settings as django_settings

from rest_framework.test import APIClient

from core.models import Service
from core.services.indexing import ensure_index_exists
from core.services.opensearch import opensearch_client

logger = logging.getLogger(__name__)


def prepare_index(index_name: str, documents: list, service: Service) -> None:
    """Prepare the search index before testing a query on it."""
    logger.info("Preparing index %s with %d documents", index_name, len(documents))

    ensure_index_exists(index_name)

    client = APIClient()
    for document in documents:
        response = client.post(
            "/api/v1.0/resources/index/",
            document,
            HTTP_AUTHORIZATION=f"Bearer {service.token}",
            format="json",
        )
        if response.status_code != 201:
            logger.error(
                "Failed to index document %s: %s",
                document["id"],
                response.content,
            )

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
