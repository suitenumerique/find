"""Tests for the service admin."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import escape

import pytest

from core import factories, models

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(name="admin_client")
def fixture_admin_client(client, settings):
    """A client logged in as a superuser, rendering admin pages without collectstatic"""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    User.objects.create_superuser(username="admin", password="admin123")
    client.login(username="admin", password="admin123")
    return client


def test_admin_services_add_shows_token_once(admin_client):
    """Adding a service should show its token, which is only stored hashed."""
    response = admin_client.post(
        reverse("admin:core_service_add"), {"name": "docs", "is_active": "on"}
    )

    assert response.status_code == 200
    service = models.Service.objects.get(name="docs")
    token = response.context["services"][0].token
    assert len(token) == 50
    assert escape(token) in response.content.decode()
    assert service.token_hash == models.hash_token(token)

    response = admin_client.get(reverse("admin:core_service_change", args=[service.pk]))
    assert response.status_code == 200
    assert escape(token) not in response.content.decode()
    assert service.token_hash not in response.content.decode()


def test_admin_services_change_keeps_token(admin_client):
    """Changing a service should neither change nor show its token."""
    service = factories.ServiceFactory(name="docs")

    response = admin_client.post(
        reverse("admin:core_service_change", args=[service.pk]),
        {"name": "drive", "is_active": "on"},
    )

    assert response.status_code == 302
    stored = models.Service.objects.get(pk=service.pk)
    assert stored.name == "drive"
    assert stored.token_hash == service.token_hash


def test_admin_services_regenerate_tokens(admin_client):
    """The action should replace the tokens of the selected services and show them."""
    services = factories.ServiceFactory.create_batch(2)
    other_service = factories.ServiceFactory()

    response = admin_client.post(
        reverse("admin:core_service_changelist"),
        {
            "action": "regenerate_tokens",
            "_selected_action": [service.pk for service in services],
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    for service, shown in zip(
        sorted(services, key=lambda s: s.pk),
        sorted(response.context["services"], key=lambda s: s.pk),
        strict=True,
    ):
        stored = models.Service.objects.get(pk=service.pk)
        assert shown.token != service.token
        assert escape(shown.token) in content
        assert stored.token_hash == models.hash_token(shown.token)

    stored = models.Service.objects.get(pk=other_service.pk)
    assert stored.token_hash == other_service.token_hash


def test_admin_services_regenerate_tokens_all_or_nothing(admin_client):
    """If a token cannot be saved, no token of the selection should be replaced."""
    services = factories.ServiceFactory.create_batch(2)
    save = models.Service.save
    calls = []

    def failing_save(service, *args, **kwargs):
        calls.append(service.pk)
        if len(calls) == 2:
            raise RuntimeError("database error")
        save(service, *args, **kwargs)

    with (
        mock.patch.object(models.Service, "save", failing_save),
        pytest.raises(RuntimeError),
    ):
        admin_client.post(
            reverse("admin:core_service_changelist"),
            {
                "action": "regenerate_tokens",
                "_selected_action": [service.pk for service in services],
            },
        )

    assert len(calls) == 2
    for service in services:
        stored = models.Service.objects.get(pk=service.pk)
        assert stored.token_hash == service.token_hash
