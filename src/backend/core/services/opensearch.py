"""OpenSearch common utilities."""

import logging
from functools import cache

from django.conf import settings

from opensearchpy import OpenSearch
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


REQUIRED_ENV_VARIABLES = [
    "OPENSEARCH_HOST",
    "OPENSEARCH_PORT",
    "OPENSEARCH_USER",
    "OPENSEARCH_PASSWORD",
    "OPENSEARCH_USE_SSL",
]


@cache
def opensearch_client():
    """Get OpenSearch client, ensuring required env variables are set"""
    missing_env_variables = [
        variable
        for variable in REQUIRED_ENV_VARIABLES
        if getattr(settings, variable, None) is None
    ]
    if missing_env_variables:
        raise ValidationError(
            f"Missing required OpenSearch environment variables: {', '.join(missing_env_variables)}"
        )

    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        timeout=50,
        use_ssl=settings.OPENSEARCH_USE_SSL,
        verify_certs=False,
    )


@cache
def check_hybrid_search_enabled():
    """Check that all required environment variables are set for hybrid search."""
    if settings.HYBRID_SEARCH_ENABLED is not True:
        logger.info("Hybrid search is disabled via HYBRID_SEARCH_ENABLED setting")
        return False

    required_vars = [
        "HYBRID_SEARCH_WEIGHTS",
        "EMBEDDING_API_PATH",
        "EMBEDDING_API_KEY",
        "EMBEDDING_API_MODEL_NAME",
        "EMBEDDING_DIMENSION",
    ]
    missing_vars = [var for var in required_vars if not getattr(settings, var, None)]
    if missing_vars:
        logger.warning(
            "Missing variables for hybrid search: %s", ", ".join(missing_vars)
        )
        return False

    return True
