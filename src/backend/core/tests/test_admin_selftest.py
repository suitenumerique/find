"""Tests for the admin selftest view."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

import pytest

from core.admin import ServiceAdminForm
from core.models import Service
from core.selftests import SelfTestResult

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def _override_storage_settings(settings):
    """Override storage settings for all tests."""
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }


def test_service_admin_form_enables_slug_on_creation():
    """The service slug must be explicit when adding a service in admin."""
    form = ServiceAdminForm()

    assert not form.fields["slug"].disabled


@patch("django.forms.models.model_to_dict", return_value={})
def test_service_admin_form_disables_slug_after_creation(_mock_model_to_dict):
    """The service slug must be read-only when editing an existing service in admin."""
    service = Service(pk=1, name="Test Service", slug="testidx")
    form = ServiceAdminForm(instance=service)

    assert form.fields["slug"].disabled


def test_selftest_requires_authentication(client):
    """Test that the selftest page requires authentication."""
    selftest_url = reverse("admin:selftest")

    response = client.get(selftest_url)

    # Should redirect to login
    assert response.status_code == 302
    assert response.url == "/admin/login/?next=/admin/selftest/"


def test_selftest_requires_staff_permission(client):
    """Test that only staff users can access the selftest page."""
    selftest_url = reverse("admin:selftest")

    User.objects.create_user(
        username="user",
        email="user@example.com",
        password="user123",
    )
    client.login(username="user", password="user123")

    response = client.get(selftest_url)

    # Regular users should be redirected
    assert response.status_code == 302
    assert response.url == "/admin/login/?next=/admin/selftest/"


def test_selftest_accessible_by_admin(client):
    """Test that admin users can access the selftest page."""
    selftest_url = reverse("admin:selftest")

    User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin123",
    )
    client.login(username="admin", password="admin123")

    response = client.get(selftest_url)

    assert response.status_code == 200
    assert b"System Self-Tests" in response.content


def test_selftest_displays_available_tests(client):
    """Test that available tests are displayed when not running."""
    selftest_url = reverse("admin:selftest")

    User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin123",
    )
    client.login(username="admin", password="admin123")

    response = client.get(selftest_url)

    assert response.status_code == 200
    assert b"Available Tests" in response.content
    assert b"Run All Tests" in response.content


@patch("core.selftests.registry.run_all")
def test_selftest_runs_tests(mock_run_all, client):
    """Test that tests are executed when run=true."""
    selftest_url = reverse("admin:selftest")

    # Mock the test results
    mock_run_all.return_value = [
        SelfTestResult(
            name="Test 1",
            success=True,
            message="Success",
            duration_ms=10.0,
        ),
        SelfTestResult(
            name="Test 2",
            success=False,
            message="Failed",
            duration_ms=20.0,
        ),
    ]

    User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin123",
    )
    client.login(username="admin", password="admin123")

    response = client.get(selftest_url, {"run": "true"})

    assert response.status_code == 200
    assert b"Test Results" in response.content
    assert b"Test 1" in response.content
    assert b"Test 2" in response.content
    mock_run_all.assert_called_once()


@patch("core.selftests.registry.run_all")
def test_selftest_displays_success_status(mock_run_all, client):
    """Test that success status is displayed correctly."""
    selftest_url = reverse("admin:selftest")

    mock_run_all.return_value = [
        SelfTestResult(
            name="Test 1",
            success=True,
            message="Success",
            duration_ms=10.0,
        ),
    ]

    User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin123",
    )
    client.login(username="admin", password="admin123")

    response = client.get(selftest_url, {"run": "true"})

    assert response.status_code == 200
    assert b"All tests passed successfully" in response.content


@patch("core.selftests.registry.run_all")
def test_selftest_displays_failure_status(mock_run_all, client):
    """Test that failure status is displayed correctly."""
    selftest_url = reverse("admin:selftest")

    mock_run_all.return_value = [
        SelfTestResult(
            name="Test 1",
            success=False,
            message="Failed",
            duration_ms=10.0,
        ),
    ]

    User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin123",
    )
    client.login(username="admin", password="admin123")

    response = client.get(selftest_url, {"run": "true"})

    assert response.status_code == 200
    assert b"Some tests failed" in response.content
