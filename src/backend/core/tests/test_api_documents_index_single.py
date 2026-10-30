"""Tests indexing documents in OpenSearch over the API"""

import datetime

from django.test import Client
from django.utils import timezone

import pytest
from opensearchpy import NotFoundError

from core import factories
from core.services import opensearch

pytestmark = pytest.mark.django_db


def test_api_documents_index_single_anonymous():
    """Anonymous requests should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = Client().post(
        "/api/v1.0/documents/index/", document, content_type="application/json"
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


def test_api_documents_index_single_invalid_token():
    """Requests with invalid tokens should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION="Bearer invalid",
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


def test_api_documents_index_single_regenerated_token():
    """The previous token of a service should be rejected once regenerated."""
    service = factories.ServiceFactory()
    old_token = service.token
    service.set_token()
    service.save()
    document = factories.DocumentSchemaFactory.build()

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {old_token:s}",
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


def test_api_documents_index_single_success():
    """A registered service should be able to index a document with a valid token."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build(title="  The Quick Brown Fox  ")

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json() == {"status": "created", "_id": str(document["id"])}

    indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )
    assert indexed_document["_version"] == 1
    source = indexed_document["_source"]
    # Datetimes are sent over JSON with millisecond precision
    for field in ["created_at", "updated_at"]:
        assert datetime.datetime.fromisoformat(source.pop(field)) == document[
            field
        ].replace(microsecond=document[field].microsecond // 1000 * 1000)
    # The title is stripped and lowercased
    assert source == {
        "title.en": "the quick brown fox",
        "content.en": document["content"],
        "depth": document["depth"],
        "path": document["path"],
        "numchild": document["numchild"],
        "size": document["size"],
        "users": document["users"],
        "groups": document["groups"],
        "reach": document["reach"],
        "tags": [],
        "is_active": True,
    }


@pytest.mark.parametrize(
    "title, content, language_code",
    [
        ("The quick brown fox", "jumps over the lazy dog", "en"),
        ("Le renard brun", "saute par-dessus le chien paresseux", "fr"),
        ("Der schnelle braune Fuchs", "springt über den faulen Hund", "de"),
        ("De snelle bruine vos", "springt over de luie hond", "nl"),
        # Detection confidence is too low
        ("planning", "", "und"),
    ],
)
def test_api_documents_index_single_language_detection(title, content, language_code):
    """
    Title and content should be stored under fields suffixed with the detected
    language, falling back to "und" when the detection is not confident enough.
    """
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build(title=title, content=content)

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 201

    source = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )["_source"]
    assert source[f"title.{language_code}"] == title.lower()
    assert source[f"content.{language_code}"] == content
    # Only the detected language is indexed
    assert [key for key in source if key.startswith(("title.", "content."))] == [
        f"title.{language_code}",
        f"content.{language_code}",
    ]


def test_api_documents_index_and_reindex_same_document():
    """
    Indexing the same document twice should update it.
    If the detected language changes the new language code should be used and the
    former language code should not be present anymore.
    """
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    # First indexing with an unrecognized language
    document["title"] = "planning"
    document["content"] = ""
    Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    new_indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )
    assert new_indexed_document["_version"] == 1
    assert (
        new_indexed_document["_source"]["title.und"]
        == document["title"].strip().lower()
    )
    assert new_indexed_document["_source"]["content.und"] == document["content"].strip()

    # Index the same document with a french content
    document["content"] = "du contenu en francais"
    Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    new_indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )
    assert new_indexed_document["_version"] == 2
    # the document is detected as french
    assert (
        new_indexed_document["_source"]["title.fr"] == document["title"].strip().lower()
    )
    assert new_indexed_document["_source"]["content.fr"] == document["content"]
    # und field are removed
    assert "title.und" not in new_indexed_document["_source"]
    assert "content.und" not in new_indexed_document["_source"]


def test_api_documents_index_single_ensure_index():
    """A registered service should be created the opensearch index if needed."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()
    opensearch_client_ = opensearch.opensearch_client()

    with pytest.raises(NotFoundError):
        opensearch_client_.indices.get(index=service.index_name)

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])

    # The index has been rebuilt
    data = opensearch_client_.indices.get(index=service.index_name)

    assert data[service.index_name]["mappings"] == {
        "dynamic": "strict",
        "properties": {
            "content": {
                "properties": {
                    "de": {
                        "type": "text",
                        "fields": {
                            "trigrams": {"type": "text", "analyzer": "trigram_analyzer"}
                        },
                        "analyzer": "german_analyzer",
                    },
                    "en": {
                        "type": "text",
                        "fields": {
                            "trigrams": {"type": "text", "analyzer": "trigram_analyzer"}
                        },
                        "analyzer": "english_analyzer",
                    },
                    "fr": {
                        "type": "text",
                        "fields": {
                            "trigrams": {"type": "text", "analyzer": "trigram_analyzer"}
                        },
                        "analyzer": "french_analyzer",
                    },
                    "nl": {
                        "type": "text",
                        "fields": {
                            "trigrams": {"type": "text", "analyzer": "trigram_analyzer"}
                        },
                        "analyzer": "dutch_analyzer",
                    },
                    "und": {
                        "type": "text",
                        "fields": {
                            "trigrams": {"type": "text", "analyzer": "trigram_analyzer"}
                        },
                        "analyzer": "undetermined_language_analyzer",
                    },
                }
            },
            "created_at": {"type": "date"},
            "depth": {"type": "integer"},
            "groups": {"type": "keyword"},
            "id": {"type": "keyword"},
            "is_active": {"type": "boolean"},
            "numchild": {"type": "integer"},
            "path": {"type": "keyword", "fields": {"text": {"type": "text"}}},
            "reach": {"type": "keyword"},
            "size": {"type": "long"},
            "tags": {"type": "keyword"},
            "title": {
                "properties": {
                    "de": {
                        "type": "keyword",
                        "fields": {
                            "text": {
                                "type": "text",
                                "fields": {
                                    "trigrams": {
                                        "type": "text",
                                        "analyzer": "trigram_analyzer",
                                    }
                                },
                                "analyzer": "german_analyzer",
                            }
                        },
                    },
                    "en": {
                        "type": "keyword",
                        "fields": {
                            "text": {
                                "type": "text",
                                "fields": {
                                    "trigrams": {
                                        "type": "text",
                                        "analyzer": "trigram_analyzer",
                                    }
                                },
                                "analyzer": "english_analyzer",
                            }
                        },
                    },
                    "fr": {
                        "type": "keyword",
                        "fields": {
                            "text": {
                                "type": "text",
                                "fields": {
                                    "trigrams": {
                                        "type": "text",
                                        "analyzer": "trigram_analyzer",
                                    }
                                },
                                "analyzer": "french_analyzer",
                            }
                        },
                    },
                    "nl": {
                        "type": "keyword",
                        "fields": {
                            "text": {
                                "type": "text",
                                "fields": {
                                    "trigrams": {
                                        "type": "text",
                                        "analyzer": "trigram_analyzer",
                                    }
                                },
                                "analyzer": "dutch_analyzer",
                            }
                        },
                    },
                    "und": {
                        "type": "keyword",
                        "fields": {
                            "text": {
                                "type": "text",
                                "fields": {
                                    "trigrams": {
                                        "type": "text",
                                        "analyzer": "trigram_analyzer",
                                    }
                                },
                                "analyzer": "undetermined_language_analyzer",
                            }
                        },
                    },
                }
            },
            "updated_at": {"type": "date"},
            "users": {"type": "keyword"},
        },
    }


@pytest.mark.parametrize(
    "field, invalid_value, error_type, error_message",
    [
        (
            "id",
            "0f9b1c9d-030f-427a-8a0e-6b7c202c5daz",  # invalid UUID b/c contains a z*
            "uuid_parsing",
            "Input should be a valid UUID, invalid character: found `z` at 36",
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
            ("Input should be a valid list"),
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
            ("Input should be a valid list"),
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
def test_api_documents_index_single_invalid_document(
    field, invalid_value, error_type, error_message
):
    """Test document indexing with various invalid fields."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    # Modify the document with the invalid value for the specified field
    document[field] = invalid_value

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()[0]["msg"] == error_message
    assert response.json()[0]["type"] == error_type


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
def test_api_documents_index_single_required(field):
    """Test document indexing with a required field missing."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    del document[field]

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()[0]["msg"] == "Field required"
    assert response.json()[0]["type"] == "missing"


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
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    del document[field]

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])

    indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )["_source"]
    assert indexed_document[field] == default_value


def test_api_documents_index_single_udpated_at_before_created():
    """Test document indexing with updated_at before created_at."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    document["updated_at"] = document["created_at"] - datetime.timedelta(seconds=1)

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert (
        response.json()[0]["msg"]
        == "Value error, updated_at must be later than created_at"
    )
    assert response.json()[0]["type"] == "value_error"


@pytest.mark.parametrize(
    "field",
    ["created_at", "updated_at"],
)
def test_api_documents_index_single_datetime_future(field):
    """Test document indexing with datetimes in the future."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    now = timezone.now()
    document[field] = now + datetime.timedelta(seconds=3)

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert (
        response.json()[0]["msg"] == f"Value error, {field:s} must be earlier than now"
    )
    assert response.json()[0]["type"] == "value_error"


def test_api_documents_index_empty_content_check():
    """Test document indexing with both empty title & content."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    document["content"] = ""
    document["title"] = ""

    response = Client().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert (
        response.json()[0]["msg"]
        == "Value error, Either title or content should have at least 1 character"
    )
    assert response.json()[0]["type"] == "value_error"
