"""Tests for service isolation (unit tests with mocked OpenSearch)."""

from unittest.mock import MagicMock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories

pytestmark = pytest.mark.django_db


class TestIndexServiceIsolation:
    """Test service field is correctly set during document indexing."""

    def test_index_document_service_field_from_auth_not_payload(
        self, mock_opensearch_client: MagicMock
    ) -> None:
        """Service field in payload is ignored; auth token determines service."""
        service = factories.ServiceFactory(name="docs-service")
        document = factories.DocumentFactory.build(service="spoofed-drive")

        response = APIClient().post(
            "/api/v1.0/documents/index/",
            document,
            HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify that the document sent to OpenSearch has service from auth, not payload
        mock_opensearch_client.index.assert_called_once()
        call_kwargs = mock_opensearch_client.index.call_args.kwargs
        indexed_body = call_kwargs["body"]
        assert indexed_body["service"] == "docs-service"
        assert indexed_body["service"] != "spoofed-drive"

    def test_bulk_index_rejected(
        self, mock_opensearch_client: MagicMock
    ) -> None:
        """Verify bulk indexing is rejected with 400 error."""
        service = factories.ServiceFactory(name="my-docs")
        n_documents = 3
        documents = factories.DocumentFactory.build_batch(n_documents, service="attempt-spoof")

        response = APIClient().post(
            "/api/v1.0/documents/index/",
            documents,
            HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "Bulk indexing not supported. Send a single document."
        
        # Verify OpenSearch was not called
        mock_opensearch_client.bulk.assert_not_called()
