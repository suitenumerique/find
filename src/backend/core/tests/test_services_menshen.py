"""
Test suite for the Menshen authentication service
"""

import base64
import time
from unittest import mock
from urllib.parse import parse_qs

from django.core.cache import cache

import pytest
import requests
import responses
from asgiref.sync import async_to_sync

from core.services.menshen import (
    MenshenUnavailable,
    MenshenUser,
    authenticate_token,
    get_cache_key,
)

from .utils import MENSHEN_TOKEN, setup_menshen_introspection

authenticate = async_to_sync(authenticate_token)


@pytest.fixture(autouse=True)
def clear_cache():
    """Introspection results are cached: start each test with an empty cache"""
    cache.clear()


@responses.activate
def test_services_menshen_valid_token(settings):
    """A valid token should authenticate its user with the granted scopes."""
    setup_menshen_introspection(
        responses, settings, scope="find:docs:search find:drive:search"
    )

    user = authenticate(MENSHEN_TOKEN)

    assert user == MenshenUser(
        sub="user_sub",
        scopes=("find:docs:search", "find:drive:search"),
        client_id="docs",
    )
    assert user.is_authenticated is True

    # Find introspects the token with its own Menshen credentials
    request = responses.calls[0].request
    credentials = base64.b64encode(b"find:find-secret").decode()
    assert request.headers["Authorization"] == f"Basic {credentials}"
    assert parse_qs(request.body)["token"] == [MENSHEN_TOKEN]


@responses.activate
def test_services_menshen_cached(settings):
    """A token should only be introspected once while its result is cached."""
    introspection = setup_menshen_introspection(responses, settings)

    assert authenticate(MENSHEN_TOKEN) == authenticate(MENSHEN_TOKEN)
    assert introspection.call_count == 1


@pytest.mark.parametrize(
    "exp_in, cache_ttl, expected_timeout",
    [
        (300, 30, 30),
        (300, 10, 10),
        # Never cached beyond the token's expiration
        (5, 30, 5),
    ],
)
@responses.activate
def test_services_menshen_cache_timeout(settings, exp_in, cache_ttl, expected_timeout):
    """Results should be cached for the configured TTL, at most until exp."""
    now = int(time.time())
    settings.MENSHEN_INTROSPECTION_CACHE_TTL = cache_ttl
    setup_menshen_introspection(responses, settings, exp=now + exp_in)

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
@responses.activate
def test_services_menshen_cache_expires(settings, exp_in, cache_ttl, expected_timeout):
    """Menshen should be called again once the cached result expires."""
    now = time.time()
    settings.MENSHEN_INTROSPECTION_CACHE_TTL = cache_ttl
    introspection = setup_menshen_introspection(
        responses, settings, exp=int(now) + exp_in
    )

    # The clock of both the service and the cache
    with mock.patch("time.time", return_value=now) as clock:
        authenticate(MENSHEN_TOKEN)

        clock.return_value = now + expected_timeout - 1
        authenticate(MENSHEN_TOKEN)
        assert introspection.call_count == 1

        clock.return_value = now + expected_timeout + 1
        authenticate(MENSHEN_TOKEN)
        assert introspection.call_count == 2


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
@responses.activate
def test_services_menshen_rejected(settings, introspection):
    """Rejected tokens should not authenticate, and be cached as rejected."""
    mocked = setup_menshen_introspection(responses, settings, **introspection)

    assert authenticate(MENSHEN_TOKEN) is None
    assert authenticate(MENSHEN_TOKEN) is None
    assert mocked.call_count == 1


@pytest.mark.parametrize("token", ["", " ", f"{MENSHEN_TOKEN} with spaces"])
@responses.activate
def test_services_menshen_malformed_token(settings, token):
    """Malformed tokens should be rejected without calling Menshen."""
    introspection = setup_menshen_introspection(responses, settings)

    assert authenticate(token) is None
    assert introspection.call_count == 0


@responses.activate
def test_services_menshen_token_format_refused(settings):
    """
    Tokens whose format Menshen refuses should be rejected, and cached as rejected.
    The format is only checked by Menshen, so Find accepts whatever it accepts.
    """
    setup_menshen_introspection(responses, settings)
    responses.replace(
        responses.POST,
        "https://menshen.example.com/auth/token/introspect/",
        status=422,
    )

    assert authenticate("too-short") is None
    assert authenticate("too-short") is None
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        {"status": 500},
        # Find's credentials are wrong
        {"status": 401},
        {"body": "not json"},
        {"body": requests.Timeout()},
        {"body": requests.ConnectionError()},
    ],
    ids=["server-error", "unauthorized", "invalid-json", "timeout", "unreachable"],
)
@responses.activate
def test_services_menshen_unavailable(settings, response):
    """Menshen failures should raise MenshenUnavailable, and not be cached."""
    setup_menshen_introspection(responses, settings)
    responses.replace(
        responses.POST, "https://menshen.example.com/auth/token/introspect/", **response
    )

    for _ in range(2):
        with pytest.raises(MenshenUnavailable):
            authenticate(MENSHEN_TOKEN)

    assert len(responses.calls) == 2
