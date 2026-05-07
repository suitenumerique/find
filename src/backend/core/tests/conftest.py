"""Fixtures for tests in the find core application"""

import pytest
from faker import Faker
from opensearchpy.exceptions import NotFoundError

from core.services import opensearch

fake = Faker()


@pytest.fixture(autouse=True)
def cleanup_test_index(settings):
    """
    Fixture to set a randomized index name for tests and remove it on tear down.
    """
    original_index = settings.OPENSEARCH_INDEX
    test_index = "".join(fake.random_letters(5)).lower()
    settings.OPENSEARCH_INDEX = test_index

    # Create client here to prevent "teardown" issues when the opensearch settings are
    # removed for error tests.
    client = opensearch.opensearch_client()

    yield

    settings.OPENSEARCH_INDEX = original_index

    try:
        client.indices.delete(index=test_index)
    except NotFoundError:
        pass
