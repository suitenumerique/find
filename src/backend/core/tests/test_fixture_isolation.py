"""Tests verifying the cleanup_test_index fixture behaviour."""

from django.conf import settings

import pytest

from core.services.indexing import ensure_index_exists
from core.services.opensearch import opensearch_client

pytestmark = pytest.mark.django_db


def test_cleanup_test_index_wipes_per_service_indices():
    """Wildcard teardown removes all per-service indices created under the test prefix."""
    client = opensearch_client()
    prefix = settings.OPENSEARCH_INDEX_PREFIX

    for svc in ("svc-a", "svc-b"):
        ensure_index_exists(f"{prefix}-{svc}")
        client.index(  # pylint: disable=unexpected-keyword-arg
            index=f"{prefix}-{svc}",
            id="doc-1",
            body={"service": svc, "title.en": "test doc"},
            refresh=True,
        )

    assert client.indices.exists(index=f"{prefix}-svc-a")
    assert client.indices.exists(index=f"{prefix}-svc-b")

    client.indices.delete(  # pylint: disable=unexpected-keyword-arg
        index=f"{prefix}-*",
        ignore_unavailable=True,
        allow_no_indices=True,
    )

    assert not client.indices.exists(index=f"{prefix}-svc-a")
    assert not client.indices.exists(index=f"{prefix}-svc-b")
