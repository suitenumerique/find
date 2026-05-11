"""Tests for service isolation (unit tests with mocked OpenSearch)."""

from unittest.mock import MagicMock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories

from ...utils_opensearch import mock_bulk_response

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

    def test_bulk_index_service_field_from_auth_not_payload(
        self, mock_opensearch_client: MagicMock
    ) -> None:
        """Verify service field is correctly set for bulk indexing."""
        service = factories.ServiceFactory(name="my-docs")
        n_documents = 3
        documents = factories.DocumentFactory.build_batch(n_documents, service="attempt-spoof")

        mock_opensearch_client.bulk.return_value = mock_bulk_response(
            items=[
                {"index": {"_id": doc["id"], "status": 201}}
                for doc in documents
            ],
            errors=False,
        )

        response = APIClient().post(
            "/api/v1.0/documents/index/",
            documents,
            HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify that all documents sent to OpenSearch have service from auth, not payload
        mock_opensearch_client.bulk.assert_called_once()
        call_kwargs = mock_opensearch_client.bulk.call_args.kwargs
        bulk_body = call_kwargs["body"]

        # bulk body is [action, doc, action, doc, ...] pattern
        for i in range(n_documents):
            doc_body = bulk_body[i * 2 + 1]  # Skip the action dict
            assert doc_body["service"] == "my-docs"
            assert doc_body["service"] != "attempt-spoof"
