"""Tests for the service registry module."""

import os

import pytest
from pydantic import ValidationError

from core.services.registry import (
    Service,
    ServiceRegistry,
    get_registry,
    get_service_by_name,
    get_service_by_token,
)


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch: pytest.MonkeyPatch):
    """Reset the registry cache and clear all SERVICES__* env vars before each test."""
    get_registry.cache_clear()
    for key in list(os.environ.keys()):
        if key.startswith("SERVICES__"):
            monkeypatch.delenv(key, raising=False)
    yield
    get_registry.cache_clear()


class TestServiceModel:
    """Tests for the Service pydantic model."""

    def test_valid_service(self):
        """Test creating a valid service."""
        service = Service(client_id="impress", token="secret123")
        assert service.client_id == "impress"
        assert service.token == "secret123"

    def test_empty_token_rejected(self):
        """Test that empty token is rejected."""
        with pytest.raises(ValidationError):
            Service(client_id="impress", token="")

    def test_empty_client_id_rejected(self):
        """Test that empty client_id is rejected."""
        with pytest.raises(ValidationError):
            Service(client_id="", token="secret123")

    def test_extra_fields_ignored(self):
        """Test that extra fields are silently ignored (extra='ignore')."""
        service = Service(client_id="impress", token="secret", unknown_field="value")
        assert service.client_id == "impress"
        assert service.token == "secret"
        assert not hasattr(service, "unknown_field")


class TestServiceRegistry:
    """Tests for ServiceRegistry env var parsing."""

    def test_single_service(self, monkeypatch: pytest.MonkeyPatch):
        """Test parsing a single service from env vars."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "abc123")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        registry = ServiceRegistry()
        
        assert "docs" in registry.services
        assert registry.services["docs"].token == "abc123"
        assert registry.services["docs"].client_id == "impress"

    def test_multiple_services(self, monkeypatch: pytest.MonkeyPatch):
        """Test parsing multiple services from env vars."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "token1")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        monkeypatch.setenv("SERVICES__DRIVE__TOKEN", "token2")
        monkeypatch.setenv("SERVICES__DRIVE__CLIENT_ID", "drive")
        
        registry = ServiceRegistry()
        
        assert len(registry.services) == 2
        assert "docs" in registry.services
        assert "drive" in registry.services

    def test_empty_registry(self):
        """Test that empty registry (no SERVICES__* vars) is valid."""
        registry = ServiceRegistry()
        assert registry.services == {}

    def test_case_normalization(self, monkeypatch: pytest.MonkeyPatch):
        """Test that service names are normalized to lowercase."""
        monkeypatch.setenv("SERVICES__DoCs__TOKEN", "abc")
        monkeypatch.setenv("SERVICES__DoCs__CLIENT_ID", "impress")
        
        registry = ServiceRegistry()
        
        assert "docs" in registry.services
        assert "DoCs" not in registry.services

    def test_duplicate_tokens_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """Test that duplicate tokens raise ValueError."""
        monkeypatch.setenv("SERVICES__A__TOKEN", "same_token")
        monkeypatch.setenv("SERVICES__A__CLIENT_ID", "client_a")
        monkeypatch.setenv("SERVICES__B__TOKEN", "same_token")
        monkeypatch.setenv("SERVICES__B__CLIENT_ID", "client_b")
        
        with pytest.raises(ValidationError) as exc_info:
            ServiceRegistry()
        assert "Duplicate token: services 'a' and 'b' have the same token" in str(exc_info.value)

    def test_invalid_service_name_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """Test that service names with hyphens are rejected."""
        monkeypatch.setenv("SERVICES__INVALID-NAME__TOKEN", "abc")
        monkeypatch.setenv("SERVICES__INVALID-NAME__CLIENT_ID", "client")
        
        with pytest.raises(ValidationError) as exc_info:
            ServiceRegistry()
        assert "Invalid service name 'invalid-name': must match pattern ^[a-z0-9_]+$" in str(exc_info.value)


class TestServiceLookup:
    """Tests for service lookup methods."""

    def test_get_by_token_found(self, monkeypatch: pytest.MonkeyPatch):
        """Test get_by_token returns (name, Service) when found."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "mytoken")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        registry = ServiceRegistry()
        result = registry.get_by_token("mytoken")
        
        assert result is not None
        name, service = result
        assert name == "docs"
        assert service.token == "mytoken"
        assert service.client_id == "impress"

    def test_get_by_token_not_found(self, monkeypatch: pytest.MonkeyPatch):
        """Test get_by_token returns None when not found."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "mytoken")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        registry = ServiceRegistry()
        
        assert registry.get_by_token("wrong_token") is None

    def test_get_by_name_found(self, monkeypatch: pytest.MonkeyPatch):
        """Test get_by_name returns Service when found."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "mytoken")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        registry = ServiceRegistry()
        result = registry.get_by_name("docs")
        
        assert result is not None
        assert result.token == "mytoken"
        assert result.client_id == "impress"

    def test_get_by_name_not_found(self, monkeypatch: pytest.MonkeyPatch):
        """Test get_by_name returns None when not found."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "mytoken")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        registry = ServiceRegistry()
        
        assert registry.get_by_name("unknown") is None

    def test_get_by_name_case_insensitive(self, monkeypatch: pytest.MonkeyPatch):
        """Test get_by_name is case insensitive."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "mytoken")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        registry = ServiceRegistry()
        
        for name in ("docs", "DOCS", "DoCs"):
            service = registry.get_by_name(name)
            assert service is not None
            assert service.token == "mytoken"
            assert service.client_id == "impress"


class TestRegistrySingleton:
    """Tests for the registry singleton pattern."""

    def test_get_registry_returns_singleton(self, monkeypatch: pytest.MonkeyPatch):
        """Test that get_registry returns the same instance."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "abc")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        registry1 = get_registry()
        registry2 = get_registry()
        
        assert registry1 is registry2

    def test_convenience_functions(self, monkeypatch: pytest.MonkeyPatch):
        """Test module-level convenience functions."""
        monkeypatch.setenv("SERVICES__DOCS__TOKEN", "mytoken")
        monkeypatch.setenv("SERVICES__DOCS__CLIENT_ID", "impress")
        
        result = get_service_by_token("mytoken")
        assert result is not None
        name, service = result
        assert name == "docs"
        assert service.token == "mytoken"
        assert service.client_id == "impress"
        
        service = get_service_by_name("docs")
        assert service is not None
        assert service.token == "mytoken"
        assert service.client_id == "impress"
