"""Tests for single-document indexing API endpoint."""

import pytest
from rest_framework.test import APIClient

from core import factories

pytestmark = pytest.mark.django_db


def test_api_resources_index_anonymous():
    """Anonymous requests should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post("/api/v1.0/resources/index/", document, format="json")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


def test_api_resources_index_invalid_token():
    """Requests with invalid tokens should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post(
        "/api/v1.0/resources/index/",
        document,
        HTTP_AUTHORIZATION="Bearer invalid",
        format="json",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


def test_api_resources_index_success():
    """A registered service should be able to index a single document with a valid token."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post(
        "/api/v1.0/resources/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    assert response.json() == {"status": "created", "_id": document["id"]}


def test_api_resources_index_bulk_rejected():
    """Bulk indexing (array input) should be rejected with 400."""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    response = APIClient().post(
        "/api/v1.0/resources/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Expected object, got array."}


def test_api_resources_index_invalid_document():
    """Invalid document should return 400 with validation errors."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()
    document["id"] = "0f9b1c9d-030f-427a-8a0e-6b7c202c5daz"  # invalid UUID (contains z)

    response = APIClient().post(
        "/api/v1.0/resources/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "uuid_parsing",
            "loc": ["id"],
            "msg": (
                "Input should be a valid UUID, invalid character: expected an optional "
                "prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `z` at 36"
            ),
        }
    ]
