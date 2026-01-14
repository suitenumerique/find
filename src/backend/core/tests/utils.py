"""Utility functions for Test."""

import base64
import json
import logging
from functools import partial

from core.management.commands.create_search_pipeline import (
    ensure_search_pipeline_exists,
)
from core.services.opensearch import (
    check_hybrid_search_enabled,
)

logger = logging.getLogger(__name__)


def enable_hybrid_search(settings):
    """Enable hybrid search settings for tests."""
    settings.HYBRID_SEARCH_ENABLED = True
    settings.HYBRID_SEARCH_WEIGHTS = [0.3, 0.7]
    settings.EMBEDDING_API_KEY = "test-api-key"
    settings.EMBEDDING_API_PATH = "https://test.embedding.api/v1/embeddings"
    settings.EMBEDDING_REQUEST_TIMEOUT = 10
    settings.EMBEDDING_API_MODEL_NAME = "embeddings-small"
    settings.EMBEDDING_DIMENSION = 1024

    # Clear the cache here or the hybrid search will remain disabled
    check_hybrid_search_enabled.cache_clear()
    ensure_search_pipeline_exists()


def build_authorization_bearer(token="some_token"):
    """
    Build an Authorization Bearer header value from a token.

    This can be used like this:
    client.post(
        ...
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer('some_token')}",
    )
    """
    return base64.b64encode(token.encode("utf-8")).decode("utf-8")


def setup_oicd_resource_server(
    responses,
    settings,
    sub="some_sub",
    audience="some_client_id",
    introspect=None,
):  # pylint: disable=too-many-arguments
    """
    Setup settings for a resource server.
    Simulate a token introspection.
    NOTE : Use it with @responses.activate or the fake introspection view will not work.
    """
    token_data = {
        "sub": sub,
        "iss": "https://oidc.example.com",
        "aud": audience,
        "client_id": audience,
        "scope": "docs",
        "active": True,
    }

    settings.OIDC_RS_ENCRYPTION_KEY_TYPE = "RSA"
    settings.OIDC_RS_ENCRYPTION_ENCODING = "A256GCM"
    settings.OIDC_RS_ENCRYPTION_ALGO = "RSA-OAEP"
    settings.OIDC_RS_SIGNING_ALGO = "RS256"
    settings.OIDC_RS_CLIENT_ID = audience
    settings.OIDC_RS_CLIENT_SECRET = "some_client_secret"
    settings.OIDC_RS_SCOPES = ["openid", "docs", "email"]

    settings.OIDC_OP_URL = "https://oidc.example.com"
    settings.OIDC_OP_INTROSPECTION_ENDPOINT = "https://oidc.example.com/introspect"

    settings.OIDC_VERIFY_SSL = False
    settings.OIDC_TIMEOUT = 5
    settings.OIDC_PROXY = None
    settings.OIDC_CREATE_USER = False

    if callable(introspect):
        responses.add_callback(
            responses.POST,
            settings.OIDC_OP_INTROSPECTION_ENDPOINT,
            callback=partial(introspect, user_info=token_data),
        )
    else:
        responses.add(
            responses.POST,
            settings.OIDC_OP_INTROSPECTION_ENDPOINT,
            body=json.dumps(token_data),
        )
