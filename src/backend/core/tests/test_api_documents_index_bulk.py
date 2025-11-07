"""Tests indexing documents in OpenSearch over the API"""

import datetime
from unittest import mock

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from core import factories
from core.services import opensearch

pytestmark = pytest.mark.django_db


def test_api_documents_index_bulk_anonymous():
    """Anonymous requests should not be allowed to index documents in bulk."""
    documents = factories.DocumentSchemaFactory.build_batch(3)

    response = APIClient().post("/api/v1.0/documents/index/", documents, format="json")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


def test_api_documents_index_bulk_invalid_token():
    """Requests with invalid tokens should not be allowed to index documents in bulk."""
    documents = factories.DocumentSchemaFactory.build_batch(3)

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION="Bearer invalid",
        format="json",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


def test_api_documents_index_bulk_success():
    """A registered service should be able to index documents in bulk with a valid token."""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    responses = response.json()
    assert [d["status"] for d in responses] == ["success"] * 3


def test_api_documents_index_bulk_ensure_index():
    """A registered service should be create the opensearch index if need."""
    opensearch_client_ = opensearch.opensearch_client()
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    with pytest.raises(opensearch.NotFoundError):
        opensearch_client_.indices.get(index=service.index_name)

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    responses = response.json()
    assert len(responses) == 3
    assert [d["status"] for d in responses] == ["success"] * 3

    # The index has been rebuilt
    opensearch_client_.indices.get(index=service.index_name)


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
        (
            "depth",
            -1,
            "greater_than_equal",
            "Input should be greater than or equal to 0",
        ),
        (
            "depth",
            "a",
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
        ),
        (
            "path",
            "a" * 301,
            "string_too_long",
            "String should have at most 300 characters",
        ),
        (
            "numchild",
            -1,
            "greater_than_equal",
            "Input should be greater than or equal to 0",
        ),
        (
            "numchild",
            "a",
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
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
            ["a" * 51],
            "string_too_long",
            "String should have at most 50 characters",
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
        (
            "is_active",
            "invalid",
            "bool_parsing",
            "Input should be a valid boolean, unable to interpret input",
        ),
    ],
)
def test_api_documents_index_bulk_invalid_document(
    field, invalid_value, error_type, error_message
):
    """Test bulk document indexing with various invalid fields."""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    # Modify the first document with the invalid value for the specified field
    documents[0][field] = invalid_value

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()
    assert [d["status"] for d in responses] == ["error", "valid", "valid"]

    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert responses[0]["errors"][0]["msg"] == error_message
    assert responses[0]["errors"][0]["type"] == error_type


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "title",
        "depth",
        "path",
        "numchild",
        "content",
        "size",
        "created_at",
        "updated_at",
        "is_active",
    ],
)
def test_api_documents_index_bulk_required(field):
    """Test bulk document indexing with a required field missing."""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    del documents[0][field]

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()
    assert [d["status"] for d in responses] == ["error", "valid", "valid"]

    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert responses[0]["errors"][0]["msg"] == "Field required"
    assert responses[0]["errors"][0]["type"] == "missing"


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
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    del documents[0][field]

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    responses = response.json()
    assert [d["status"] for d in responses] == ["success"] * 3

    indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=responses[0]["_id"]
    )["_source"]
    assert indexed_document[field] == default_value


def test_api_documents_index_bulk_updated_at_before_created_at():
    """Test bulk document indexing with updated_at before created_at."""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    documents[0]["updated_at"] = documents[0]["created_at"] - datetime.timedelta(
        seconds=1
    )

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()

    assert [d["status"] for d in responses] == ["error", "valid", "valid"]

    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert (
        responses[0]["errors"][0]["msg"]
        == "Value error, updated_at must be later than created_at"
    )
    assert responses[0]["errors"][0]["type"] == "value_error"


@pytest.mark.parametrize(
    "field",
    ["created_at", "updated_at"],
)
def test_api_documents_index_bulk_datetime_future(field):
    """Test bulk document indexing with datetimes in the future."""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    now = timezone.now()
    documents[0][field] = now + datetime.timedelta(seconds=3)

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()
    assert [d["status"] for d in responses] == ["error", "valid", "valid"]

    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert (
        responses[0]["errors"][0]["msg"]
        == f"Value error, {field:s} must be earlier than now"
    )
    assert responses[0]["errors"][0]["type"] == "value_error"


def test_api_documents_index_empty_content_check():
    """Test bulk document indexing with both empty title & content."""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    documents[0]["content"] = ""
    documents[0]["title"] = ""

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    responses = response.json()
    assert [d["status"] for d in responses] == ["error", "valid", "valid"]

    assert responses[0]["status"] == "error"
    assert len(responses[0]["errors"]) == 1
    assert (
        responses[0]["errors"][0]["msg"]
        == "Value error, Either title or content should have at least 1 character"
    )
    assert responses[0]["errors"][0]["type"] == "value_error"


def test_api_documents_index_opensearch_errors():
    """Test bulk document indexing errors"""
    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(3)

    with mock.patch.object(opensearch.opensearch_client(), "bulk") as mock_bulk:
        mock_bulk.return_value = {
            "items": [
                {"index": {"status": 201}},
                {
                    "index": {
                        "status": 400,
                    }
                },
                {"index": {"status": 403, "error": {"reason": "This is forbidden"}}},
            ]
        }

        response = APIClient().post(
            "/api/v1.0/documents/index/",
            documents,
            HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
            format="json",
        )

    assert response.status_code == 201
    responses = response.json()
    assert responses == [
        {
            "_id": documents[0]["id"],
            "index": 0,
            "status": "success",
        },
        {
            "_id": documents[1]["id"],
            "index": 1,
            "status": "error",
            "message": "Unknown error",
        },
        {
            "_id": documents[2]["id"],
            "index": 2,
            "status": "error",
            "message": "This is forbidden",
        },
    ]
