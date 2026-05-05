"""Tests for service configuration models."""

import pytest
from pydantic import ValidationError

from core.services.config import ServiceConfig, ServicesConfig


class TestServicesConfigLookups:
    def test_get_by_token(self):
        docs = ServiceConfig(name="docs", token="docs-token-xyz", client_id="docs-client")
        config = ServicesConfig(service=[docs])

        assert config.get_by_token("docs-token-xyz") == docs

    def test_get_by_token_not_found(self):
        docs = ServiceConfig(name="docs", token="docs-token", client_id="docs-client")
        config = ServicesConfig(service=[docs])

        assert config.get_by_token("nonexistent") is None

    def test_get_by_client_id(self):
        drive = ServiceConfig(name="drive", token="drive-token-abc", client_id="drive-client-id")
        config = ServicesConfig(service=[drive])

        assert config.get_by_client_id("drive-client-id") == drive

    def test_get_by_client_id_not_found(self):
        drive = ServiceConfig(name="drive", token="drive-token", client_id="drive-client")
        config = ServicesConfig(service=[drive])

        assert config.get_by_client_id("nonexistent") is None

    def test_multiple_services_token_lookup(self):
        docs = ServiceConfig(name="docs", token="docs-secret-token", client_id="docs-client-id")
        drive = ServiceConfig(name="drive", token="drive-secret-token", client_id="drive-client-id")
        mail = ServiceConfig(name="mail", token="mail-secret-token", client_id="mail-client-id")
        config = ServicesConfig(service=[docs, drive, mail])

        assert config.get_by_token("docs-secret-token") == docs
        assert config.get_by_token("drive-secret-token") == drive
        assert config.get_by_token("mail-secret-token") == mail
        assert config.get_by_token("non-existent-token") is None


class TestServicesConfigValidation:
    def test_name_slugified_lowercase(self):
        service = ServiceConfig(name="MyService", token="token-value", client_id="client-value")
        expected = ServiceConfig(name="myservice", token="token-value", client_id="client-value")

        assert service == expected

    def test_name_with_spaces_slugified(self):
        service = ServiceConfig(name="My Service", token="token-value", client_id="client-value")
        expected = ServiceConfig(name="my-service", token="token-value", client_id="client-value")

        assert service == expected

    def test_empty_token_string_fails_validation(self):
        with pytest.raises(ValidationError, match="token"):
            ServiceConfig(name="empty", token="", client_id="client-value")

    def test_empty_client_id_string_fails_validation(self):
        with pytest.raises(ValidationError, match="client_id"):
            ServiceConfig(name="empty", token="token-value", client_id="")

    def test_empty_name_string_fails_validation(self):
        with pytest.raises(ValidationError, match="name"):
            ServiceConfig(name="", token="token-value", client_id="client-value")
