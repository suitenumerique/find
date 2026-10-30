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


def regenerate_tokens(admin_client, services):
    """Run the regenerate action on services, following redirects"""
    return admin_client.post(
        reverse("admin:core_service_changelist"),
        {
            "action": "regenerate_tokens",
            "_selected_action": [service.pk for service in services],
        },
        follow=True,
    )


def test_admin_services_regenerate_tokens_concurrent_change(admin_client):
    """
    If a token changed since the selection was read, as when two administrators
    regenerate it at once, no token of the selection should be replaced: the
    token shown to the other administrator must keep working.
    """
    services = factories.ServiceFactory.create_batch(2)
    set_token = models.Service.set_token
    new_tokens = []

    def set_token_concurrently(service, *args, **kwargs):
        # The first token is saved, then the second one was changed meanwhile
        if new_tokens:
            models.Service.objects.filter(pk=service.pk).update(
                token_hash=models.hash_token("concurrent-token")
            )
        new_tokens.append(set_token(service, *args, **kwargs))
        return new_tokens[-1]

    with mock.patch.object(models.Service, "set_token", set_token_concurrently):
        response = regenerate_tokens(admin_client, services)

    assert response.templates[0].name == "admin/change_list.html"
    assert "A token was changed meanwhile" in response.content.decode()
    assert len(new_tokens) == 2
    stored_hashes = set(models.Service.objects.values_list("token_hash", flat=True))
    assert not stored_hashes & {models.hash_token(token) for token in new_tokens}
    for token in new_tokens:
        assert escape(token) not in response.content.decode()


def test_admin_services_regenerate_tokens_render_failure(admin_client):
    """If the tokens cannot be shown, they should not replace the old ones."""
    services = factories.ServiceFactory.create_batch(2)

    with (
        mock.patch(
            "core.admin.ServiceAdmin.render_tokens",
            side_effect=RuntimeError("template error"),
        ),
        pytest.raises(RuntimeError),
    ):
        regenerate_tokens(admin_client, services)

    for service in services:
        stored = models.Service.objects.get(pk=service.pk)
        assert stored.token_hash == service.token_hash


@pytest.mark.parametrize(
    "button,next_url_name,next_label",
    [
        ("_continue", "admin:core_service_change", "Continue editing"),
        ("_addanother", "admin:core_service_add", "Add another service"),
    ],
)
def test_admin_services_add_and_continue(
    admin_client, button, next_url_name, next_label
):
    """
    Saving and continuing should still show the token, with a link to the
    next step instead of going there directly.
    """
    response = admin_client.post(
        reverse("admin:core_service_add"),
        {"name": "docs", "is_active": "on", button: "1"},
    )

    assert response.status_code == 200
    service = models.Service.objects.get(name="docs")
    token = response.context["services"][0].token
    assert service.token_hash == models.hash_token(token)
    args = [service.pk] if next_url_name == "admin:core_service_change" else []
    assert f'<a href="{reverse(next_url_name, args=args)}">{next_label}</a>' in (
        response.content.decode()
    )


def test_admin_services_no_add_from_popup(admin_client):
    """
    Services cannot be added from the allowed services field: the popup would
    close without showing the token.
    """
    response = admin_client.get(reverse("admin:core_service_add"))

    assert response.status_code == 200
    assert 'id="add_id_services"' not in response.content.decode()
