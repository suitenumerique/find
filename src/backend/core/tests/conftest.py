"""Fixtures for tests in the find core application"""

import pytest
from faker import Faker
from opensearchpy.exceptions import NotFoundError

from core.services import opensearch

fake = Faker()


@pytest.fixture(autouse=True)
def cleanup_test_index(settings):
    """
    Fixture to set a randomized index prefix for tests and remove it on tear down.
    """
    original_prefix = settings.OPENSEARCH_INDEX_PREFIX
    test_prefix = "".join(fake.random_letters(5)).lower()
    settings.OPENSEARCH_INDEX_PREFIX = test_prefix

    # Client must be created here to prevent teardown issues when opensearch settings
    # are removed for error tests.
    client = opensearch.opensearch_client()

    yield

    settings.OPENSEARCH_INDEX_PREFIX = original_prefix

    try:
        client.indices.delete(index=f"{test_prefix}-*")
    except NotFoundError:
        pass
