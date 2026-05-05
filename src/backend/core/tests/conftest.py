"""Fixtures for tests in the find core application"""

from django.utils.text import slugify

import pytest
from faker import Faker
from lasuite.oidc_resource_server.authentication import (
    get_resource_server_backend,
)
from opensearchpy.exceptions import NotFoundError

from core.services import opensearch
from core.services.config import ServiceConfig, ServicesSettings

fake = Faker()


@pytest.fixture
def create_service(monkeypatch):
    """
    Factory fixture to create service configs for testing.

    Usage:
        service = create_service()  # Creates with random defaults
        service = create_service(name="docs", token="my-token", client_id="impress")

    Returns a ServiceConfig with .token, .client_id, .name, and .index_name properties.
    Automatically patches services_settings in authentication and indexing modules.
    """
    services_settings = ServicesSettings()

    monkeypatch.setattr("core.authentication.services_settings", services_settings)
    monkeypatch.setattr("core.services.indexing.services_settings", services_settings)

    def _create(name=None, token=None, client_id=None, **kwargs):
        if name is None:
            name = slugify(fake.word())
        else:
            name = slugify(name)
        if token is None:
            token = "".join(fake.random_letters(32))
        if client_id is None:
            client_id = fake.word()

        config = ServiceConfig(token=token, client_id=client_id, name=name)
        services_settings.services[name] = config
        return config

    return _create


@pytest.fixture(name="jwt_rs_backend")
def jwt_resource_server_backend_fixture(settings):
    """Fixture to switch the backend to the JWTResourceServerBackend."""
    _original_backend = str(settings.OIDC_RS_BACKEND_CLASS)

    settings.OIDC_RS_BACKEND_CLASS = (
        "lasuite.oidc_resource_server.backend.JWTResourceServerBackend"
    )
    get_resource_server_backend.cache_clear()

    yield

    settings.OIDC_RS_BACKEND_CLASS = _original_backend
    get_resource_server_backend.cache_clear()


@pytest.fixture(autouse=True)
def cleanup_test_index(settings):
    """
    Fixture to set a randomized prefix for all service indexes within the tests
    and remove them on tear down.
    """
    _original_prefix = settings.OPENSEARCH_INDEX_PREFIX
    prefix = "".join(fake.random_letters(5)).lower()
    settings.OPENSEARCH_INDEX_PREFIX = prefix

    # Create client here to prevent "teardown" issues when the opensearch settings are
    # removed for error tests.
    client = opensearch.opensearch_client()

    yield

    settings.OPENSEARCH_INDEX_PREFIX = _original_prefix

    try:
        client.indices.delete(index=f"{prefix}-*")
    except NotFoundError:
        pass
