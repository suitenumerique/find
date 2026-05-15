from unittest.mock import MagicMock

from django.conf import LazySettings

import pytest
from django_bolt.testing import TestClient

from core.services.opensearch import opensearch_client

pytestmark = pytest.mark.django_db


class TestDeleteDocumentHandler:
    @pytest.mark.vcr
    def test_delete_existing_document_returns_204(
        self,
        settings: LazySettings,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        client = opensearch_client()
        client.index(
            index=settings.OPENSEARCH_INDEX,
            id="doc-123",
            body={
                "title.en": "Test Document",
                "content.en": "Test content",
                "is_active": True,
                "service": "test-service",
            },
            refresh=True,
        )

        response = bolt_client.delete(
            "/api/v1.0/documents/doc-123",
            headers={"Authorization": "Token service-token"},
        )

        assert response.status_code == 204
        assert response.text == ""

    @pytest.mark.vcr
    def test_delete_nonexistent_document_returns_404(
        self,
        settings: LazySettings,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
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

    @pytest.mark.vcr
    def test_delete_with_uuid_document_id(
        self,
        settings: LazySettings,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        doc_id = "550e8400-e29b-41d4-a716-446655440000"

        client = opensearch_client()
        client.index(
            index=settings.OPENSEARCH_INDEX,
            id=doc_id,
            body={
                "title.en": "UUID Document",
                "content.en": "Test content",
                "is_active": True,
                "service": "test-service",
            },
            refresh=True,
        )

        response = bolt_client.delete(
            f"/api/v1.0/documents/{doc_id}",
            headers={"Authorization": "Token service-token"},
        )

        assert response.status_code == 204
        assert response.text == ""
