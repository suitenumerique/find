from unittest.mock import MagicMock

from django.conf import LazySettings

import pytest
from django_bolt.testing import TestClient
from opensearchpy.exceptions import NotFoundError

pytestmark = pytest.mark.django_db


class TestDeleteDocumentHandler:
    def test_delete_existing_document_returns_204(
        self,
        settings: LazySettings,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        mock_opensearch_client.delete.return_value = {"result": "deleted"}

        response = bolt_client.delete(
            "/api/v1.0/documents/doc-123",
            headers={"Authorization": "Token service-token"},
        )

        assert response.status_code == 204
        assert response.text == ""
        mock_opensearch_client.delete.assert_called_once_with(
            index=settings.OPENSEARCH_INDEX,
            id="doc-123",
        )

    def test_delete_nonexistent_document_returns_404(
        self,
        settings: LazySettings,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        error = NotFoundError(404, "document_missing_exception", {"_id": "doc-456"})
        mock_opensearch_client.delete.side_effect = error

        response = bolt_client.delete(
            "/api/v1.0/documents/doc-456",
            headers={"Authorization": "Token service-token"},
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Document not found"}

    def test_delete_without_auth_returns_401(
        self,
        mock_opensearch_client: MagicMock,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.delete("/api/v1.0/documents/doc-123")

        assert response.status_code == 401
        assert response.json() == {"detail": "Service authentication required"}
        mock_opensearch_client.delete.assert_not_called()

    def test_delete_with_uuid_document_id(
        self,
        settings: LazySettings,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        doc_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_opensearch_client.delete.return_value = {"result": "deleted"}

        response = bolt_client.delete(
            f"/api/v1.0/documents/{doc_id}",
            headers={"Authorization": "Token service-token"},
        )

        assert response.status_code == 204
        assert response.text == ""
        mock_opensearch_client.delete.assert_called_once_with(
            index=settings.OPENSEARCH_INDEX,
            id=doc_id,
        )
