"""Authentication of the user tokens exchanged with Menshen for Find (ADR-0001)."""

import asyncio
import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus

from django.conf import settings
from django.core.cache import cache

import requests
from menshen_client import Configuration, IntrospectionRequest, TokenExchangeClient
from menshen_client.exceptions import ResponseParsingError

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "menshen:introspection"
# Only rejects obvious garbage: the token format is Menshen's to check, which
# answers 422 to tokens it does not accept
TOKEN_PATTERN = re.compile(r"\S+")
# Cached for tokens Menshen rejected, which cannot become valid again
REJECTED = "rejected"

# requests sessions are not guaranteed to be thread-safe, so each thread running
# an introspection gets its own client
_clients = threading.local()


class MenshenUnavailable(Exception):
    """Menshen could not tell whether a token is valid."""


@dataclass(frozen=True)
class MenshenUser:
    """A user authenticated by a token exchanged with Menshen."""

    sub: str
    scopes: tuple[str, ...]
    # The calling service, to identify it in logs, never for authorization
    client_id: str | None = None
    is_authenticated: bool = field(default=True, init=False)


def get_client():
    """Get the Menshen client of the current thread for the current settings"""
    config = Configuration(
        client_id=settings.MENSHEN_CLIENT_ID,
        client_secret=settings.MENSHEN_CLIENT_SECRET,
        server_root_url=settings.MENSHEN_URL,
        requests_timeout=settings.MENSHEN_TIMEOUT,
    )
    client = getattr(_clients, "client", None)
    if client is None or client.config != config:
        client = TokenExchangeClient(config)
        _clients.client = client
    return client


def get_cache_key(token):
    """Cache key of a token's introspection, without the token itself"""
    return f"{CACHE_KEY_PREFIX}:{hashlib.sha256(token.encode()).hexdigest()}"


def introspect(token):
    """
    Introspect a token with Menshen.

    Returns:
        The introspection response, or None if Menshen refused the token format.

    Raises:
        MenshenUnavailable: if Menshen could not introspect the token.
    """
    try:
        return get_client().introspect(IntrospectionRequest(token=token))
    except requests.HTTPError as error:
        if error.response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
            logger.warning("Menshen refused the format of a token")
            return None
        logger.error("Menshen could not introspect a token: %s", error)
        raise MenshenUnavailable() from error
    except (requests.RequestException, ResponseParsingError) as error:
        logger.error("Menshen could not introspect a token: %s", error)
        raise MenshenUnavailable() from error


def get_user(response, now):
    """Get the user of an introspection response, or None if it must be rejected"""
    if not response.active or not response.sub:
        return None
    if response.exp is None or response.exp <= now:
        logger.warning("Rejected a Menshen token expired or without exp")
        return None
    if response.aud != settings.MENSHEN_AUDIENCE:
        logger.warning("Rejected a Menshen token for audience %s", response.aud)
        return None
    return MenshenUser(
        sub=response.sub,
        scopes=tuple((response.scope or "").split()),
        client_id=response.client_id,
    )


async def authenticate_token(token):
    """
    Authenticate a user token exchanged with Menshen.

    Introspection results are cached for MENSHEN_INTROSPECTION_CACHE_TTL seconds,
    never beyond the token's expiration. Rejected tokens are cached too.

    Returns:
        The MenshenUser of the token, or None if the token is rejected.

    Raises:
        MenshenUnavailable: if Menshen could not introspect the token.
    """
    if not TOKEN_PATTERN.fullmatch(token):
        return None

    cache_key = get_cache_key(token)
    cached = await cache.aget(cache_key)
    if cached is not None:
        return None if cached == REJECTED else cached

    response = await asyncio.to_thread(introspect, token)
    now = int(time.time())
    user = None if response is None else get_user(response, now)

    timeout = settings.MENSHEN_INTROSPECTION_CACHE_TTL
    if user is None:
        await cache.aset(cache_key, REJECTED, timeout)
    else:
        logger.info("Authenticated a Menshen token from %s", user.client_id)
        await cache.aset(cache_key, user, min(timeout, response.exp - now))
    return user
