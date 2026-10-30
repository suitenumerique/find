"""OpenSearch common utilities."""

import asyncio
import logging
import weakref
from functools import cache

from django.conf import settings

from asgiref.sync import async_to_sync
from opensearchpy import AsyncOpenSearch, OpenSearch
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


REQUIRED_ENV_VARIABLES = [
    "OPENSEARCH_HOST",
    "OPENSEARCH_PORT",
    "OPENSEARCH_USER",
    "OPENSEARCH_PASSWORD",
    "OPENSEARCH_USE_SSL",
]

# AsyncOpenSearch holds an aiohttp session bound to the event loop it was first used
# in, so clients cannot be shared between loops.
_async_clients = weakref.WeakKeyDictionary()


def get_client_options():
    """Get OpenSearch client options, ensuring required env variables are set"""
    missing_env_variables = [
        variable
        for variable in REQUIRED_ENV_VARIABLES
        if getattr(settings, variable, None) is None
    ]
    if missing_env_variables:
        raise ValidationError(
            f"Missing required OpenSearch environment variables: {', '.join(missing_env_variables)}"
        )

    return {
        "hosts": [{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        "http_auth": (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        "timeout": 50,
        "use_ssl": settings.OPENSEARCH_USE_SSL,
        "verify_certs": False,
    }


@cache
def opensearch_client():
    """Get OpenSearch client"""
    return OpenSearch(**get_client_options())


def async_opensearch_client():
    """Get the AsyncOpenSearch client of the running event loop"""
    loop = asyncio.get_running_loop()
    client = _async_clients.get(loop)
    if client is None:
        client = AsyncOpenSearch(**get_client_options())
        _async_clients[loop] = client
    return client


async def close_async_opensearch_client():
    """Close the AsyncOpenSearch client of the running event loop, if any"""
    client = _async_clients.pop(asyncio.get_running_loop(), None)
    if client is not None:
        await client.close()


def run_async(func, *args, **kwargs):
    """
    Run an async function from sync code, in its own event loop, and close the
    AsyncOpenSearch client of this loop afterwards.

    Only needed while the views are synchronous (ADR-0001).
    """

    async def wrapper():
        try:
            return await func(*args, **kwargs)
        finally:
            await close_async_opensearch_client()

    return async_to_sync(wrapper)()
