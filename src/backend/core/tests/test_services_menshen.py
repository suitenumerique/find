"""
Test suite for the Menshen authentication service
"""

import asyncio
import base64
import time
from unittest import mock
from urllib.parse import parse_qs

from django.core.cache import cache

import httpx2
import pytest
from asgiref.sync import async_to_sync

from core.services import menshen
from core.services.menshen import (
    MenshenUnavailable,
    MenshenUser,
    authenticate_token,
    get_cache_key,
)

from .utils import (
    MENSHEN_INTROSPECTION_URL,
    MENSHEN_TOKEN,
    setup_menshen,
    setup_menshen_introspection,
)

authenticate = async_to_sync(authenticate_token)


def test_services_menshen_client_per_event_loop(settings):
    """
    The client should be shared within an event loop, replaced when the settings
    change, and closed by close_client.
    """
    setup_menshen(settings)

    async def get_clients():
        client = await menshen.get_client()
        same_client = await menshen.get_client()
        settings.MENSHEN_TIMEOUT = 1.0
        new_client = await menshen.get_client()
        await menshen.close_client()
        return client, same_client, new_client, asyncio.get_running_loop()

    client, same_client, new_client, loop = async_to_sync(get_clients)()

    assert client is same_client
    assert new_client is not client
    assert new_client.config.requests_timeout == 1.0
    assert client.session.is_closed
    assert new_client.session.is_closed
    # Other tests may leave the clients of their event loops until collected
    assert loop not in menshen._clients  # pylint: disable=protected-access


def test_services_menshen_valid_token(settings, httpx2_mock):
    """A valid token should authenticate its user with the granted scopes."""
    setup_menshen_introspection(
        httpx2_mock, settings, scope="find:docs:search find:drive:search"
    )

    user = authenticate(MENSHEN_TOKEN)

    assert user == MenshenUser(
        sub="user_sub",
        scopes=("find:docs:search", "find:drive:search"),
        client_id="docs",
    )
    assert user.is_authenticated is True

    # Find introspects the token with its own Menshen credentials
    (request,) = httpx2_mock.get_requests()
    credentials = base64.b64encode(b"find:find-secret").decode()
    assert request.headers["Authorization"] == f"Basic {credentials}"
    assert parse_qs(request.content.decode())["token"] == [MENSHEN_TOKEN]


def test_services_menshen_cached(settings, httpx2_mock):
    """A token should only be introspected once while its result is cached."""
    setup_menshen_introspection(httpx2_mock, settings)

    assert authenticate(MENSHEN_TOKEN) == authenticate(MENSHEN_TOKEN)
    assert len(httpx2_mock.get_requests()) == 1


@pytest.mark.parametrize(
    "exp_in, cache_ttl, expected_timeout",
    [
        (300, 30, 30),
        (300, 10, 10),
        # Never cached beyond the token's expiration
        (5, 30, 5),
    ],
)
def test_services_menshen_cache_timeout(
    settings, httpx2_mock, exp_in, cache_ttl, expected_timeout
):
    """Results should be cached for the configured TTL, at most until exp."""
    now = int(time.time())
    settings.MENSHEN_INTROSPECTION_CACHE_TTL = cache_ttl
    setup_menshen_introspection(httpx2_mock, settings, exp=now + exp_in)

    with (
        mock.patch("core.services.menshen.time.time", return_value=now),
        mock.patch.object(cache, "aset", new_callable=mock.AsyncMock) as aset,
    ):
        user = authenticate(MENSHEN_TOKEN)

    aset.assert_called_once_with(get_cache_key(MENSHEN_TOKEN), user, expected_timeout)


@pytest.mark.parametrize(
    "exp_in, cache_ttl, expected_timeout",
    [
        (300, 30, 30),
        (300, 10, 10),
        # Never cached beyond the token's expiration
        (5, 30, 5),
    ],
)
def test_services_menshen_cache_expires(
    settings, httpx2_mock, exp_in, cache_ttl, expected_timeout
):
    """Menshen should be called again once the cached result expires."""
    now = time.time()
    settings.MENSHEN_INTROSPECTION_CACHE_TTL = cache_ttl
    setup_menshen_introspection(httpx2_mock, settings, exp=int(now) + exp_in)

    # The clock of both the service and the cache
    with mock.patch("time.time", return_value=now) as clock:
        authenticate(MENSHEN_TOKEN)

        clock.return_value = now + expected_timeout - 1
        authenticate(MENSHEN_TOKEN)
        assert len(httpx2_mock.get_requests()) == 1

        clock.return_value = now + expected_timeout + 1
        authenticate(MENSHEN_TOKEN)
        assert len(httpx2_mock.get_requests()) == 2


def test_services_menshen_cache_key_hides_token():
    """The cache key should not contain the token."""
    assert MENSHEN_TOKEN not in get_cache_key(MENSHEN_TOKEN)
    assert get_cache_key(MENSHEN_TOKEN) != get_cache_key(f"{MENSHEN_TOKEN}-other")


@pytest.mark.parametrize(
    "introspection",
    [
        {"active": False},
        {"sub": ""},
        {"exp": int(time.time()) - 1},
        {"aud": "docs"},
        {"aud": None},
    ],
    ids=["inactive", "no-sub", "expired", "other-audience", "no-audience"],
)
def test_services_menshen_rejected(settings, httpx2_mock, introspection):
    """Rejected tokens should not authenticate, and be cached as rejected."""
    setup_menshen_introspection(httpx2_mock, settings, **introspection)

    assert authenticate(MENSHEN_TOKEN) is None
    assert authenticate(MENSHEN_TOKEN) is None
    assert len(httpx2_mock.get_requests()) == 1


@pytest.mark.parametrize("token", ["", " ", f"{MENSHEN_TOKEN} with spaces"])
def test_services_menshen_malformed_token(settings, httpx2_mock, token):
    """Malformed tokens should be rejected without calling Menshen."""
    setup_menshen_introspection(httpx2_mock, settings)

    assert authenticate(token) is None
    assert not httpx2_mock.get_requests()


def test_services_menshen_token_format_refused(settings, httpx2_mock):
    """
    Tokens whose format Menshen refuses should be rejected, and cached as rejected.
    The format is only checked by Menshen, so Find accepts whatever it accepts.
    """
    setup_menshen(settings)
    httpx2_mock.add_response(
        method="POST", url=MENSHEN_INTROSPECTION_URL, status_code=422
    )

    assert authenticate("too-short") is None
    assert authenticate("too-short") is None
    assert len(httpx2_mock.get_requests()) == 1


@pytest.mark.parametrize(
    "response",
    [
        {"status_code": 500},
        # Find's credentials are wrong
        {"status_code": 401},
        {"text": "not json"},
    ],
    ids=["server-error", "unauthorized", "invalid-json"],
)
def test_services_menshen_unavailable(settings, httpx2_mock, response):
    """Menshen failures should raise MenshenUnavailable, and not be cached."""
    setup_menshen(settings)
    httpx2_mock.add_response(
        method="POST", url=MENSHEN_INTROSPECTION_URL, is_reusable=True, **response
    )

    for _ in range(2):
        with pytest.raises(MenshenUnavailable):
            authenticate(MENSHEN_TOKEN)

    assert len(httpx2_mock.get_requests()) == 2


@pytest.mark.parametrize(
    "exception",
    [httpx2.ReadTimeout("timeout"), httpx2.ConnectError("unreachable")],
    ids=["timeout", "unreachable"],
)
def test_services_menshen_unreachable(settings, httpx2_mock, exception):
    """Menshen being unreachable should raise MenshenUnavailable, and not be cached."""
    setup_menshen(settings)
    httpx2_mock.add_exception(
        exception, method="POST", url=MENSHEN_INTROSPECTION_URL, is_reusable=True
    )

    for _ in range(2):
        with pytest.raises(MenshenUnavailable):
            authenticate(MENSHEN_TOKEN)

    assert len(httpx2_mock.get_requests()) == 2


@pytest.mark.parametrize(
    "setting", ["MENSHEN_URL", "MENSHEN_CLIENT_ID", "MENSHEN_CLIENT_SECRET"]
)
def test_services_menshen_not_configured(settings, httpx2_mock, setting):
    """An unset Menshen setting should raise MenshenUnavailable, without calling it."""
    setup_menshen(settings)
    setattr(settings, setting, None)

    with pytest.raises(MenshenUnavailable):
        authenticate(MENSHEN_TOKEN)

    assert not httpx2_mock.get_requests()
