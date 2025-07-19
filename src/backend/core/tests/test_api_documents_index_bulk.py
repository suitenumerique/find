"""Tests indexing documents in OpenSearch over the API"""

import datetime

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from core import factories, opensearch

pytestmark = pytest.mark.django_db


def test_api_documents_index_bulk_anonymous():
    """Anonymous requests should not be allowed to index documents in bulk."""
    documents = factories.DocumentSchemaFactory.build_batch(3)

    response = APIClient().post("/api/v1.0/documents/", documents, format="json")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


def test_api_documents_index_bulk_invalid_token():
    """Requests with invalid tokens should not be allowed to index documents in bulk."""
    documents = factories.DocumentSchemaFactory.build_batch(3)

    response = APIClient().post(
        "/api/v1.0/documents/",
        documents,
        HTTP_AUTHORIZATION="Bearer invalid",
        format="json",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


def test_api_documents_index_bulk_success():
    """A registered service should be able to index documents in bulk with a valid token."""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(3)

    response = APIClient().post(
        "/api/v1.0/documents/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 207
    responses = response.json()
    assert len(responses) == 3
    for result in response.json():
        assert result["status"] == "success"


@pytest.mark.parametrize(
    "field, invalid_value, error_type, error_message",
    [
        (
            "id",
            "0f9b1c9d-030f-427a-8a0e-6b7c202c5daz",  # invalid UUID b/c contains a z
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
            "Input should be a valid list",
        ),
        (
            "users",
            ["33052c8b-3181-4420-aede-f8396fc0f9az"],  # invalid UUID b/c contains a z
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
            "Input should be a valid list",
        ),
        (
            "reach",
            "invalid",
            "enum",
            "Input should be 'public', 'authenticated' or 'restricted'",
        ),
    ],
)
def test_api_documents_index_bulk_invalid_document(
    field, invalid_value, error_type, error_message
):
    """Test bulk document indexing with various invalid fields."""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(3)

    # Modify the first document with the invalid value for the specified field
    documents[0][field] = invalid_value

    response = APIClient().post(
        "/api/v1.0/documents/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()

    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert responses[0]["errors"][0]["msg"] == error_message
    assert responses[0]["errors"][0]["type"] == error_type

    for i in [1, 2]:
        assert responses[i]["status"] == "valid"


@pytest.mark.parametrize(
    "field", ["id", "title", "content", "size", "created_at", "updated_at"]
)
def test_api_documents_index_bulk_required(field):
    """Test bulk document indexing with a required field missing."""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(3)

    del documents[0][field]

    response = APIClient().post(
        "/api/v1.0/documents/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()
    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert responses[0]["errors"][0]["msg"] == "Field required"
    assert responses[0]["errors"][0]["type"] == "missing"

    for i in [1, 2]:
        assert responses[i]["status"] == "valid"


@pytest.mark.parametrize(
    "field,default_value",
    [
        ("users", []),
        ("groups", []),
        ("reach", "restricted"),
    ],
)
def test_api_documents_index_bulk_default(field, default_value):
    """Test bulk document indexing while removing optional fields that have default values."""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(3)

    del documents[0][field]

    response = APIClient().post(
        "/api/v1.0/documents/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 207
    responses = response.json()
    assert len(responses) == 3
    for result in response.json():
        assert result["status"] == "success"

    indexed_document = opensearch.client.get(
        index=service.index_name, id=responses[0]["_id"]
    )["_source"]
    assert indexed_document[field] == default_value


def test_api_documents_index_bulk_updated_at_before_created_at():
    """Test bulk document indexing with updated_at before created_at."""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(3)

    documents[0]["updated_at"] = documents[0]["created_at"] - datetime.timedelta(
        seconds=1
    )

    response = APIClient().post(
        "/api/v1.0/documents/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()
    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert (
        responses[0]["errors"][0]["msg"]
        == "Value error, updated_at must be later than created_at"
    )
    assert responses[0]["errors"][0]["type"] == "value_error"

    for i in [1, 2]:
        assert responses[i]["status"] == "valid"


@pytest.mark.parametrize(
    "field",
    ["created_at", "updated_at"],
)
def test_api_documents_index_bulk_datetime_future(field):
    """Test bulk document indexing with datetimes in the future."""
    service = factories.ServiceFactory(name="test-service")
    documents = factories.DocumentSchemaFactory.build_batch(3)

    now = timezone.now()
    documents[0][field] = now + datetime.timedelta(seconds=3)

    response = APIClient().post(
        "/api/v1.0/documents/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()
    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert (
        responses[0]["errors"][0]["msg"]
        == f"Value error, {field:s} must be earlier than now"
    )
    assert responses[0]["errors"][0]["type"] == "value_error"

    for i in [1, 2]:
        assert responses[i]["status"] == "valid"
