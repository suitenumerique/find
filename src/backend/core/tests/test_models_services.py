"""Tests ServiceConfig for find's core app."""

import pytest
from pydantic import ValidationError

from core.services.config import ServiceConfig


def test_service_config_name_slugified(settings, create_service):
    """The name field should be slugified."""
    service = create_service(name="My service name")
    assert service.name == "my-service-name"
    assert service.index_name == f"{settings.OPENSEARCH_INDEX_PREFIX}-my-service-name"


def test_service_config_name_slugified_directly():
    """ServiceConfig slugifies name when created directly."""
    config = ServiceConfig(token="test-token", client_id="test-client", name="My Name")
    assert config.name == "my-name"


def test_service_config_empty_token_rejected():
    """Empty token should be rejected at model creation."""
    with pytest.raises(ValidationError):
        ServiceConfig(token="", client_id="test-client")


def test_service_config_empty_client_id_rejected():
    """Empty client_id should be rejected at model creation."""
    with pytest.raises(ValidationError):
        ServiceConfig(token="test-token", client_id="")
