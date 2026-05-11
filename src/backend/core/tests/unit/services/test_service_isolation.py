"""Tests for service isolation (unit tests with mocked OpenSearch)."""

from django.conf import settings

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories

pytestmark = pytest.mark.django_db


class TestIndexServiceIsolation:
    """Test service field is correctly set during document indexing."""

    def test_index_document_service_field_from_auth_not_payload(
        self, mock_opensearch_client
    ):
        """Service field in payload is ignored; auth token determines service."""
        service = factories.ServiceFactory(name="docs-service")
        document = factories.DocumentFactory.build(service="spoofed-drive")

        # Configure mock to return the indexed document with correct service
        mock_opensearch_client.get.return_value = {
            "_id": document["id"],
            "_source": {**document, "service": "docs-service"},
        }

        response = APIClient().post(
            "/api/v1.0/documents/index/",
            document,
            HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        indexed_doc = mock_opensearch_client.get(
            index=settings.OPENSEARCH_INDEX, id=document["id"]
        )
        assert indexed_doc["_source"]["service"] == "docs-service"

    def test_bulk_index_service_field_from_auth_not_payload(
        self, mock_opensearch_client
    ):
        """Verify service field is correctly set for bulk indexing."""
        service = factories.ServiceFactory(name="my-docs")
        documents = factories.DocumentFactory.build_batch(3, service="attempt-spoof")

        def mock_get(index=None, id=None):  # pylint: disable=redefined-builtin,unused-argument
            for doc in documents:
                if doc["id"] == id:
                    return {
                        "_id": id,
                        "_source": {**doc, "service": "my-docs"},
                    }
            return {"_id": id, "_source": {}}

        mock_opensearch_client.get.side_effect = mock_get

        response = APIClient().post(
            "/api/v1.0/documents/index/",
            documents,
            HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        for doc in documents:
            indexed_doc = mock_opensearch_client.get(
                index=settings.OPENSEARCH_INDEX, id=doc["id"]
            )
            assert indexed_doc["_source"]["service"] == "my-docs"
