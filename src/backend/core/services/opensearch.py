"""OpenSearch common utilities."""

import logging
from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from opensearchpy import OpenSearch

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
        raise ImproperlyConfigured(
            f"Missing required OpenSearch environment variables: {', '.join(missing_env_variables)}"
        )

    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        timeout=50,
        use_ssl=settings.OPENSEARCH_USE_SSL,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        **({"ca_certs": settings.OPENSEARCH_CA_CERTS} if settings.OPENSEARCH_CA_CERTS else {}),
    )
