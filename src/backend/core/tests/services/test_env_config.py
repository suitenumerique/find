"""Tests for environment variable-based service configuration."""

import os

import pytest
from pydantic import ValidationError

from core.services.config import ServiceConfig, ServicesConfig

from find.values import ServicesValue


@pytest.fixture(autouse=True)
def clear_services_env_vars(monkeypatch):
    """Clear all SERVICES__ environment variables before each test."""
    for key in list(os.environ.keys()):
        if key.startswith("SERVICES__"):
            monkeypatch.delenv(key, raising=False)


class TestEnvVarServiceDiscovery:
    """Test service discovery from SERVICES__*__* environment variables."""

    def test_single_service_discovery(self, monkeypatch):
        """Test discovering a single service from env vars."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "abc123")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "docs-client")

        docs = ServiceConfig(name="docs", token="abc123", client_id="docs-client")
        expected = ServicesConfig(service=[docs])

        result = ServicesValue().to_python(None)

        assert result == expected

    def test_multiple_services_discovery(self, monkeypatch):
        """Test discovering multiple services from env vars."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "docs-token")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "docs-client")
        monkeypatch.setenv("SERVICES__DRIVE__TOKEN", "drive-token")
        monkeypatch.setenv("SERVICES__DRIVE__CLIENT_ID", "drive-client")

        docs = ServiceConfig(name="docs", token="docs-token", client_id="docs-client")
        drive = ServiceConfig(name="drive", token="drive-token", client_id="drive-client")

        result = ServicesValue().to_python(None)

        assert len(result.services) == 2
        assert docs in result.services
        assert drive in result.services

    def test_missing_client_id_raises_validation_error(self, monkeypatch):
        """Test that missing CLIENT_ID raises ValidationError."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "abc123")
        # Intentionally not setting CLIENT_ID

        sv = ServicesValue()

        with pytest.raises(ValidationError, match="client_id"):
            sv.to_python(None)

    def test_empty_value_raises_validation_error(self, monkeypatch):
        """Test that empty string values raise ValidationError."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "docs-client")

        sv = ServicesValue()

        with pytest.raises(ValidationError, match="token"):
            sv.to_python(None)

    def test_service_name_lowercased(self, monkeypatch):
        """Test that service names are lowercased."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "token-value")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "client-value")

        docs = ServiceConfig(name="docs", token="token-value", client_id="client-value")
        expected = ServicesConfig(service=[docs])

        result = ServicesValue().to_python(None)

        assert result == expected
