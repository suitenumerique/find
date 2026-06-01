"""Fixtures for tests in the find core application"""

import uuid

import pytest

from core.services import opensearch


@pytest.fixture(autouse=True)
def cleanup_test_index(settings):
    """
    Fixture to set a unique index prefix per test and wipe all per-service indices
    created under that prefix on teardown.
    """
    unique = uuid.uuid4().hex[:12]
    settings.OPENSEARCH_INDEX_PREFIX = f"test-{unique}"

    # Create client here to prevent teardown issues when opensearch settings are
    # removed for error tests.
    client = opensearch.opensearch_client()

    yield

    client.indices.delete(  # pylint: disable=unexpected-keyword-arg
        index=f"test-{unique}-*",
        ignore_unavailable=True,
        allow_no_indices=True,
    )
