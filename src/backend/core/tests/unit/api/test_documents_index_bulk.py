"""Tests for bulk indexing rejection (bulk indexing is no longer supported)"""

from rest_framework import status
from rest_framework.test import APIClient

from core import factories

import pytest

pytestmark = pytest.mark.django_db


def test_api_documents_index_bulk_rejected():
    """Bulk indexing should be rejected with 400 error."""
    service = factories.ServiceFactory()
    documents = factories.DocumentFactory.build_batch(3)

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Bulk indexing not supported. Send a single document."


def test_api_documents_index_bulk_anonymous_rejected():
    """Anonymous bulk requests should be rejected with 403."""
    documents = factories.DocumentFactory.build_batch(3)

    response = APIClient().post("/api/v1.0/documents/index/", documents, format="json")

    assert response.status_code == 403
    assert response.json() == {
        "type": "about:blank",
        "title": "Forbidden",
        "status": 403,
        "detail": "Authentication credentials were not provided.",
    }
