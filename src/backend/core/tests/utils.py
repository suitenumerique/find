"""Utility functions for Test."""

import base64
import logging
import time

from asgiref.sync import async_to_sync

from core import factories
from core.services.opensearch import close_async_opensearch_client

logger = logging.getLogger(__name__)


def bulk_create_documents(document_payloads):
    """Build documents owned by "user_sub" from payloads."""
    return [
        factories.DocumentSchemaFactory.build(**document_payload, users=["user_sub"])
        for document_payload in document_payloads
    ]


def run_async(func, *args, **kwargs):
    """
    Run an async service function from a sync test, in its own event loop, and
    close the AsyncOpenSearch client of this loop afterwards.
    """

    async def wrapper():
        try:
            return await func(*args, **kwargs)
        finally:
            await close_async_opensearch_client()

    return async_to_sync(wrapper)()


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
