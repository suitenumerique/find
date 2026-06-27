"""Fixtures for tests in the find core application"""

import pytest
from faker import Faker
from opensearchpy.exceptions import NotFoundError

from core.services import opensearch

fake = Faker()


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
