"""Fixtures for tests in the find core application"""

from django.utils.text import slugify

import pytest
from faker import Faker
from opensearchpy.exceptions import NotFoundError

from core.services import opensearch
from core.services.config import ServiceConfig, ServicesConfig

fake = Faker()


@pytest.fixture
def create_service(monkeypatch, settings):
    """Factory fixture to create service configs for testing."""
    config = ServicesConfig()

    # Mock settings.SERVICES with our test config
    monkeypatch.setattr(settings, "SERVICES", config)

    def _create(name=None, token=None, client_id=None, **kwargs):
        if name is None:
            name = slugify(fake.word())
        else:
            name = slugify(name)
        if token is None:
            token = "".join(fake.random_letters(32))
        if client_id is None:
            client_id = fake.word()

        service = ServiceConfig(token=token, client_id=client_id, name=name)
        config.services.append(service)
        return service

    return _create


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
