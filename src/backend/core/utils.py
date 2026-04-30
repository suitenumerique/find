"""Tests Service model for find's core app."""

import logging

from django.conf import settings as django_settings
from django.core.cache import cache

from django_redis.cache import RedisCache
from opensearchpy.exceptions import NotFoundError

from core import factories
from core.services.opensearch import opensearch_client

logger = logging.getLogger(__name__)


def throttle_acquire(name: str, timeout: int = 0, atomic: bool = True):
    """
    Acquire a throttle lock to prevent multiple batch indexation tasks during countdown.

    implements a debouncing pattern: only the first call during the timeout period
    will succeed, subsequent calls are skipped until the timeout expires.

    Args:
        name (str): Name of the throttle lock.
        timeout (int): Lock duration in seconds (countdown period).
        atomic (bool): Use Redis locks for atomic operations if available.

    Returns:
        bool: True if lock acquired (first call), False if already held (subsequent calls).
    """
    key = f"throttle-lock:{name}"

    # Redis is used as cache database (not in tests). Use the lock feature here
    # to ensure atomicity of changes to the throttle flag.
    if isinstance(cache, RedisCache) and atomic:
        with cache.client.get_client().lock(key, timeout=timeout):
            return throttle_acquire(name, timeout, atomic=False)

    # cache.add() is atomic test-and-set operation:
    #   - If key doesn't exist: creates it with timeout and returns True
    #   - If key already exists: does nothing and returns False
    # The key expires after timeout seconds, releasing the lock.
    # The value 1 is irrelevant, only the key presence/absence matters.
    return cache.add(key, 1, timeout=timeout)


def bulk_create_documents(document_payloads):
    """Create documents in bulk from payloads"""
    return [
        factories.DocumentSchemaFactory.build(**document_payload, users=["user_sub"])
        for document_payload in document_payloads
    ]


def delete_search_pipeline():
    """Delete the hybrid search pipeline if it exists"""
    logger.info(
        "Deleting search pipeline %s", django_settings.HYBRID_SEARCH_PIPELINE_ID
    )

    try:
        opensearch_client().transport.perform_request(
            method="DELETE",
            url=f"/_search/pipeline/{django_settings.HYBRID_SEARCH_PIPELINE_ID}",
        )
    except NotFoundError:
        logger.info("Search pipeline not found, nothing to delete.")


def delete_index(index_name):
    """Delete the hybrid search pipeline if it exists"""
    logger.info("Deleting Index %s", index_name)

    try:
        opensearch_client().indices.delete(index=index_name)
    except NotFoundError:
        logger.info("Search pipeline %s not found, nothing to delete.", index_name)


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


def extract_language_code(source: dict) -> str:
    """
    Extract the language code from the OpenSearch data.

    Args:
        source: Dictionary in OpenSearch format
    Returns:
        str: The extracted language code.
    """
    for language_code in django_settings.SUPPORTED_LANGUAGE_CODES:
        if f"title.{language_code}" in source:
            return language_code
    raise ValueError("No supported language code in source")
