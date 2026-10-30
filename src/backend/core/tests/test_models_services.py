"""Tests Service model for find's core app."""

import hashlib

from django.db import IntegrityError

import pytest

from core import factories, models

pytestmark = pytest.mark.django_db


def test_models_services_name_unique():
    """The name field should be unique across services."""
    service = factories.ServiceFactory()

    with pytest.raises(IntegrityError):
        factories.ServiceFactory(name=service.name)


def test_models_services_name_slugified(settings):
    """The name field should be slugified."""
    service = factories.ServiceFactory(name="My service name")
    assert service.name == "my-service-name"
    assert service.index_name == f"{settings.OPENSEARCH_INDEX_PREFIX}-my-service-name"


def test_models_services_token_generated_on_creation():
    """A 50 characters token should be generated on creation and only its hash stored."""
    service = factories.ServiceFactory()

    assert len(service.token) == 50
    assert service.token_hash == hashlib.sha256(service.token.encode()).hexdigest()

    stored = models.Service.objects.get(pk=service.pk)
    assert stored.token is None
    assert stored.token_hash == service.token_hash


def test_models_services_token_hash_unique():
    """Two services should not share a token."""
    service = factories.ServiceFactory()

    with pytest.raises(IntegrityError):
        factories.ServiceFactory(token=service.token)


def test_models_services_set_token():
    """set_token should replace the token, generating a new one if not given."""
    service = factories.ServiceFactory()
    old_hash = service.token_hash

    token = service.set_token()

    assert token == service.token
    assert len(token) == 50
    assert service.token_hash == models.hash_token(token) != old_hash

    assert service.set_token("my-token") == "my-token"
    assert service.token_hash == models.hash_token("my-token")
