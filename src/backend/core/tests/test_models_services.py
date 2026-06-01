"""Tests Service model for find's core app."""

from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError

import pytest

from core import factories

pytestmark = pytest.mark.django_db


def test_models_services_slug_unique():
    """The slug field must be unique across services."""
    service = factories.ServiceFactory()

    with pytest.raises(IntegrityError):
        factories.ServiceFactory(slug=service.slug)


def test_models_services_name_not_required_unique():
    """Two services may share the same display name."""
    factories.ServiceFactory(slug="aa", name="Same Name")
    factories.ServiceFactory(slug="bb", name="Same Name")


def test_models_services_slug_auto_derived_from_name():
    """When no slug is provided, it is auto-derived from name (alphanumeric, lowercase)."""
    service = factories.ServiceFactory(slug=None, name="My Service Name")
    assert service.slug == "myservicename"
    assert service.name == "My Service Name"


def test_models_services_slug_auto_derivation_strips_special_chars():
    """Slug derivation strips hyphens, underscores, spaces and punctuation."""
    service = factories.ServiceFactory(slug=None, name="docs-service_v2!")
    assert service.slug == "docsservicev2"


def test_models_services_slug_rejects_non_alphanumeric():
    """Explicit non-alphanumeric slugs are rejected by the DB check constraint."""
    with pytest.raises(IntegrityError):
        factories.ServiceFactory(slug="has-hyphen")


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


def test_service_slug_immutable_after_creation():
    """The slug field must be immutable after creation."""
    service = factories.ServiceFactory(slug="originalname")
    service.slug = "differentname"
    with pytest.raises(ValidationError):
        service.save()


def test_service_name_editable_after_creation():
    """The name field is freely editable after creation."""
    service = factories.ServiceFactory(slug="myslug", name="Original")
    service.name = "New Display Name"
    service.save()
    service.refresh_from_db()
    assert service.name == "New Display Name"
    assert service.slug == "myslug"
