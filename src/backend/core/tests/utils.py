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
MENSHEN_INTROSPECTION_URL = "https://menshen.example.com/auth/token/introspect/"


def setup_menshen(settings):
    """Configure Find's Menshen settings, without simulating any response."""
    settings.MENSHEN_URL = "https://menshen.example.com"
    settings.MENSHEN_CLIENT_ID = "find"
    settings.MENSHEN_CLIENT_SECRET = "find-secret"
    settings.MENSHEN_AUDIENCE = "find"


def setup_menshen_introspection(httpx2_mock, settings, **introspection):
    """
    Configure Menshen and simulate its introspection of any token, returning a
    valid token for "user_sub" called by Docs, unless overridden by the
    `introspection` fields (e.g. `active=False`, `scope="find:drive:search"`).

    The response is reusable and optional: count the introspections with
    `httpx2_mock.get_requests()`.
    """
    setup_menshen(settings)

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
    httpx2_mock.add_response(
        method="POST",
        url=MENSHEN_INTROSPECTION_URL,
        json=token_data,
        is_reusable=True,
        is_optional=True,
    )
