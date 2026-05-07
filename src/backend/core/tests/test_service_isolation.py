"""Tests for service isolation."""

from django.conf import settings

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.services.opensearch import opensearch_client

pytestmark = pytest.mark.django_db


class TestIndexServiceIsolation:
    """Test service field is correctly set during document indexing."""

    def test_index_document_service_field_from_auth_not_payload(self):
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

        client = opensearch_client()
        indexed_doc = client.get(index=settings.OPENSEARCH_INDEX, id=document["id"])
        assert indexed_doc["_source"]["service"] == "docs-service"

    def test_bulk_index_service_field_from_auth_not_payload(self):
        """Verify service field is correctly set for bulk indexing."""
        service = factories.ServiceFactory(name="my-docs")
        documents = factories.DocumentFactory.build_batch(3, service="attempt-spoof")

        response = APIClient().post(
            "/api/v1.0/documents/index/",
            documents,
            HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        client = opensearch_client()
        for doc in documents:
            indexed_doc = client.get(index=settings.OPENSEARCH_INDEX, id=doc["id"])
            assert indexed_doc["_source"]["service"] == "my-docs"
