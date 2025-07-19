"""Tests indexing documents in OpenSearch over the API"""

import datetime

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from core import factories, opensearch

pytestmark = pytest.mark.django_db


def test_api_documents_index_single_anonymous():
    """Anonymous requests should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post("/api/v1.0/documents/", document, format="json")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


def test_api_documents_index_single_invalid_token():
    """Requests with invalid tokens should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post(
        "/api/v1.0/documents/",
        document,
        HTTP_AUTHORIZATION="Bearer invalid",
        format="json",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


def test_api_documents_index_single_success():
    """A registered service should be able to index document with a valid token."""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post(
        "/api/v1.0/documents/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])


@pytest.mark.parametrize(
    "field, invalid_value, error_type, error_message",
    [
        (
            "id",
            "0f9b1c9d-030f-427a-8a0e-6b7c202c5daz",  # invalid UUID b/c contains a z*
            "uuid_parsing",
            (
                "Input should be a valid UUID, invalid character: expected an optional "
                "prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `z` at 36"
            ),
        ),
        ("title", 1, "string_type", "Input should be a valid string"),
        (
            "title",
            "a" * 301,
            "string_too_long",
            "String should have at most 300 characters",
        ),
        ("content", 1, "string_type", "Input should be a valid string"),
        (
            "created_at",
            "invalid_date",
            "datetime_from_date_parsing",
            "Input should be a valid datetime or date, invalid character in year",
        ),
        (
            "updated_at",
            "invalid_date",
            "datetime_from_date_parsing",
            "Input should be a valid datetime or date, invalid character in year",
        ),
        (
            "size",
            64448894017.3,
            "int_from_float",
            "Input should be a valid integer, got a number with a fractional part",
        ),
        (
            "size",
            "not an integer",
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
        ),
        (
            "users",
            "33052c8b-3181-4420-aede-f8396fc0f9a1",
            "list_type",
            ("Input should be a valid list"),
        ),
        (
            "users",
            ["33052c8b-3181-4420-aede-f8396fc0f9az"],  # invalid UUID b/c contains a z*
            "uuid_parsing",
            (
                "Input should be a valid UUID, invalid character: expected an optional "
                "prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `z` at 36"
            ),
        ),
        (
            "groups",
            ["not_a_slug"],
            "string_pattern_mismatch",
            "String should match pattern '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
        ),
        (
            "groups",
            "not-a-list",
            "list_type",
            ("Input should be a valid list"),
        ),
        (
            "reach",
            "invalid",
            "enum",
            "Input should be 'public', 'authenticated' or 'restricted'",
        ),
    ],
)
def test_api_documents_index_single_invalid_document(
    field, invalid_value, error_type, error_message
):
    """Test document indexing with various invalid fields."""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build()

    # Modify the document with the invalid value for the specified field
    document[field] = invalid_value

    response = APIClient().post(
        "/api/v1.0/documents/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert response.data[0]["msg"] == error_message
    assert response.data[0]["type"] == error_type


@pytest.mark.parametrize(
    "field", ["id", "title", "content", "size", "created_at", "updated_at"]
)
def test_api_documents_index_single_required(field):
    """Test document indexing with a required field missing."""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build()

    del document[field]

    response = APIClient().post(
        "/api/v1.0/documents/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert response.data[0]["msg"] == "Field required"
    assert response.data[0]["type"] == "missing"


@pytest.mark.parametrize(
    "field,default_value",
    [
        ("users", []),
        ("groups", []),
        ("reach", "restricted"),
    ],
)
def test_api_documents_index_single_default(field, default_value):
    """Test document indexing while removing optional fields that have default values."""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build()

    del document[field]

    response = APIClient().post(
        "/api/v1.0/documents/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])

    indexed_document = opensearch.client.get(
        index=service.index_name, id=str(document["id"])
    )["_source"]
    assert indexed_document[field] == default_value


def test_api_documents_index_single_udpated_at_before_created():
    """Test document indexing with updated_at before created_at."""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build()

    document["updated_at"] = document["created_at"] - datetime.timedelta(seconds=1)

    response = APIClient().post(
        "/api/v1.0/documents/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert (
        response.data[0]["msg"]
        == "Value error, updated_at must be later than created_at"
    )
    assert response.data[0]["type"] == "value_error"


@pytest.mark.parametrize(
    "field",
    ["created_at", "updated_at"],
)
def test_api_documents_index_single_datetime_future(field):
    """Test document indexing with datetimes in the future."""
    service = factories.ServiceFactory(name="test-service")
    document = factories.DocumentSchemaFactory.build()

    now = timezone.now()
    document[field] = now + datetime.timedelta(seconds=3)

    response = APIClient().post(
        "/api/v1.0/documents/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert response.data[0]["msg"] == f"Value error, {field:s} must be earlier than now"
    assert response.data[0]["type"] == "value_error"
