"""
Test suite for the authentication of services with their service token
"""

import pytest
from asgiref.sync import async_to_sync

from core import factories
from core.services.service_tokens import get_service_by_token

pytestmark = pytest.mark.django_db

# Async ORM calls run in the test thread through async_to_sync, so they see the
# data of the test transaction.
service_by_token = async_to_sync(get_service_by_token)


def test_services_service_tokens_valid_token():
    """A service's token should authenticate that service."""
    service = factories.ServiceFactory(name="docs")
    factories.ServiceFactory(name="drive")

    assert service_by_token(service.token) == service


def test_services_service_tokens_loads_whole_service():
    """The service should be fully loaded, async code cannot load deferred fields."""
    service = factories.ServiceFactory(name="docs")

    authenticated = service_by_token(service.token)

    assert authenticated.get_deferred_fields() == set()


def test_services_service_tokens_inactive_service():
    """The token of an inactive service should not authenticate it."""
    service = factories.ServiceFactory(is_active=False)

    assert service_by_token(service.token) is None


@pytest.mark.parametrize("token", ["", None, "unknown-token"])
def test_services_service_tokens_unknown_token(token):
    """Missing or unknown tokens should not authenticate any service."""
    factories.ServiceFactory()

    assert service_by_token(token) is None


def test_services_service_tokens_hash_is_not_a_token():
    """The stored hash should not be accepted as a token."""
    service = factories.ServiceFactory()

    assert service_by_token(service.token_hash) is None


def test_services_service_tokens_regenerated_token():
    """After a token is regenerated, only the new token should authenticate."""
    service = factories.ServiceFactory()
    old_token = service.token
    service.set_token()
    service.save()

    assert service_by_token(old_token) is None
    assert service_by_token(service.token) == service
