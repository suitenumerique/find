"""Utility functions for Test."""

import base64
import json
import logging
import time
from functools import partial

from core import factories

logger = logging.getLogger(__name__)


def bulk_create_documents(document_payloads):
    """Build documents owned by "user_sub" from payloads."""
    return [
        factories.DocumentSchemaFactory.build(**document_payload, users=["user_sub"])
        for document_payload in document_payloads
    ]


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


MENSHEN_TOKEN = "an-exchanged-token-with-at-least-32-characters"


def setup_menshen_introspection(responses, settings, **introspection):
    """
    Configure Menshen and simulate its introspection of any token, returning a
    valid token for "user_sub" called by Docs, unless overridden by the
    `introspection` fields (e.g. `active=False`, `scope="find:drive:search"`).
    NOTE : Use it with @responses.activate.

    Returns the mocked introspection response, to count its calls.
    """
    settings.MENSHEN_URL = "https://menshen.example.com"
    settings.MENSHEN_CLIENT_ID = "find"
    settings.MENSHEN_CLIENT_SECRET = "find-secret"
    settings.MENSHEN_AUDIENCE = "find"

    token_data = {
        "active": True,
        "sub": "user_sub",
        "scope": "find:docs:search",
        "exp": int(time.time()) + 300,
        "aud": "find",
        "client_id": "docs",
        **introspection,
    }
    if not token_data["active"]:
        # Menshen only says that inactive tokens are inactive
        token_data = {"active": False}
    return responses.add(
        responses.POST,
        "https://menshen.example.com/auth/token/introspect/",
        json=token_data,
    )
