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
    "OPENSEARCH_USE_SSL",
]


@cache
def opensearch_client():
    """Get OpenSearch client, ensuring required env variables are set.

    Supports passwordless authentication when OPENSEARCH_USER and OPENSEARCH_PASSWORD
    are not set or empty.
    """
    missing_env_variables = [
        variable
        for variable in REQUIRED_ENV_VARIABLES
        if getattr(settings, variable, None) is None
    ]
    if missing_env_variables:
        raise ValidationError(
            f"Missing required OpenSearch environment variables: {', '.join(missing_env_variables)}"
        )

    # Support passwordless auth when credentials are not configured
    user = getattr(settings, "OPENSEARCH_USER", None)
    password = getattr(settings, "OPENSEARCH_PASSWORD", None)
    http_auth = (user, password) if user and password else None

    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=http_auth,
        timeout=50,
        use_ssl=settings.OPENSEARCH_USE_SSL,
        verify_certs=False,
    )
