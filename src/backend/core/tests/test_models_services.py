"""Tests Service model for find's core app."""

from django.db import DataError, IntegrityError

import pytest

from core import factories

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


def test_models_services_token_50_characters_exact():
    """The token field should be 50 characters long."""
    service = factories.ServiceFactory()
    assert len(service.token) == 50


def test_models_services_token_50_characters_less():
    """The token field should not be less than 50 characters long."""
    with pytest.raises(IntegrityError):
        factories.ServiceFactory(token="a" * 49)


def test_models_services_token_50_characters_more():
    """The token field should be 50 characters long."""
    with pytest.raises(DataError):
        factories.ServiceFactory(token="a" * 51)
