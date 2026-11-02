"""
Test suite for the authentication of the API requests
"""

from django.test import RequestFactory

import pytest
from asgiref.sync import async_to_sync
from ninja.errors import AuthenticationError, AuthorizationError

from core import factories
from core.authentication import MenshenBearer, ServiceTokenBearer
from core.services.menshen import MenshenUnavailable, MenshenUser

from .utils import (
    MENSHEN_INTROSPECTION_URL,
    MENSHEN_TOKEN,
    setup_menshen,
    setup_menshen_introspection,
)

pytestmark = pytest.mark.django_db


def authenticate(auth, authorization=None):
    """Authenticate a request with an Authorization header, if any."""
    headers = {} if authorization is None else {"Authorization": authorization}
    request = RequestFactory().post("/", headers=headers)

    async def run():
        return await auth(request)

    # The auth classes check the header synchronously, then authenticate the
    # token asynchronously
    return async_to_sync(run)()


@pytest.mark.parametrize("authorization", [None, "", MENSHEN_TOKEN, "Basic abc"])
def test_authentication_menshen_not_provided(authorization):
    """A request without a bearer token should get a 401."""
    with pytest.raises(AuthenticationError) as error:
        authenticate(MenshenBearer(), authorization)

    assert error.value.status_code == 401
    assert str(error.value) == "Authentication credentials were not provided."


@pytest.mark.parametrize("scheme", ["Bearer", "bearer"])
def test_authentication_menshen_valid_token(settings, httpx2_mock, scheme):
    """A token accepted by Menshen should authenticate its user."""
    setup_menshen_introspection(httpx2_mock, settings, scope="find:docs:search")

    user = authenticate(MenshenBearer(), f"{scheme} {MENSHEN_TOKEN}")

    assert user == MenshenUser(
        sub="user_sub", scopes=("find:docs:search",), client_id="docs"
    )


def test_authentication_menshen_rejected_token(settings, httpx2_mock):
    """A token rejected by Menshen should get a 401."""
    setup_menshen_introspection(httpx2_mock, settings, active=False)

    with pytest.raises(AuthenticationError) as error:
        authenticate(MenshenBearer(), f"Bearer {MENSHEN_TOKEN}")

    assert error.value.status_code == 401
    assert str(error.value) == "Invalid token."


def test_authentication_menshen_unavailable(settings, httpx2_mock):
    """Menshen being unavailable should not be answered as a rejected token."""
    setup_menshen(settings)
    httpx2_mock.add_response(
        method="POST", url=MENSHEN_INTROSPECTION_URL, status_code=500
    )

    with pytest.raises(MenshenUnavailable):
        authenticate(MenshenBearer(), f"Bearer {MENSHEN_TOKEN}")


@pytest.mark.parametrize("authorization", [None, ""])
def test_authentication_service_token_not_provided(authorization):
    """A request without a service token should get a 403."""
    with pytest.raises(AuthorizationError) as error:
        authenticate(ServiceTokenBearer(), authorization)

    assert error.value.status_code == 403
    assert str(error.value) == "Authentication credentials were not provided."


@pytest.mark.parametrize("prefix", ["Bearer ", "Token ", ""])
def test_authentication_service_token_valid_token(prefix):
    """A service token should authenticate its service, with or without a scheme."""
    service = factories.ServiceFactory(name="docs")

    assert authenticate(ServiceTokenBearer(), f"{prefix}{service.token}") == service


def test_authentication_service_token_invalid_token():
    """An unknown token, or the token of an inactive service, should get a 403."""
    inactive = factories.ServiceFactory(name="docs", is_active=False)

    for token in ["invalid", inactive.token]:
        with pytest.raises(AuthorizationError) as error:
            authenticate(ServiceTokenBearer(), f"Bearer {token}")

        assert error.value.status_code == 403
        assert str(error.value) == "Invalid token."


def test_authentication_menshen_spaces_after_scheme(monkeypatch):
    """Several spaces may separate the scheme from the token (RFC 6750)."""
    tokens = []

    async def authenticate_token(token):
        tokens.append(token)
        return "user"

    monkeypatch.setattr("core.authentication.authenticate_token", authenticate_token)

    assert authenticate(MenshenBearer(), f"Bearer   {MENSHEN_TOKEN}") == "user"
    assert tokens == [MENSHEN_TOKEN]
