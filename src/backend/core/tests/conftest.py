"""Fixtures for tests in the find core application"""

import pytest
from lasuite.oidc_resource_server.authentication import (
    get_resource_server_backend,
)


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
