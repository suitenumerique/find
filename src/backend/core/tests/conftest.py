"""Fixtures for tests in the find core application"""

import pytest
from faker import Faker
from lasuite.oidc_resource_server.authentication import (
    get_resource_server_backend,
)
from opensearchpy.exceptions import NotFoundError

from core.services import opensearch

fake = Faker()


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
