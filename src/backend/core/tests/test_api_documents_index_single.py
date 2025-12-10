"""Tests indexing documents in OpenSearch over the API"""

import datetime

from django.utils import timezone

import pytest
import responses
from opensearchpy import NotFoundError
from rest_framework.test import APIClient

from core import factories
from core.services import opensearch
from core.tests.mock import albert_embedding_response
from core.tests.utils import enable_hybrid_search

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear caches and delete search pipeline before each test"""
    opensearch.check_hybrid_search_enabled.cache_clear()


def test_api_documents_index_single_anonymous():
    """Anonymous requests should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post("/api/v1.0/documents/index/", document, format="json")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


def test_api_documents_index_single_invalid_token():
    """Requests with invalid tokens should not be allowed to index documents."""
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION="Bearer invalid",
        format="json",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


@responses.activate
def test_api_documents_index_single_hybrid_enabled_success(settings):
    """
    A registered service should be able to index document with a valid token.
    If hybrid search is enabled, the documents are chunked and embedded.
    """
    service = factories.ServiceFactory()
    enable_hybrid_search(settings)
    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    document = factories.DocumentSchemaFactory.build()
    document["content"] = (
        "a long text to embed." * 100
    )  # Ensure content is long enough for chunking

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])

    new_indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )
    assert new_indexed_document["_version"] == 1

    assert (
        new_indexed_document["_source"]["title.en"] == document["title"].strip().lower()
    )
    assert new_indexed_document["_source"]["content.en"] == document["content"]
    # only the english fields are indexed
    assert not "content.fr" in new_indexed_document["_source"]

    # check embedding
    assert (
        new_indexed_document["_source"]["chunks"][0]["embedding"]
        == albert_embedding_response.response["data"][0]["embedding"]
    )
    assert (
        new_indexed_document["_source"]["embedding_model"]
        == settings.EMBEDDING_API_MODEL_NAME
    )
    # Check that the document has been chunked correctly
    assert (
        len(new_indexed_document["_source"]["chunks"])
        == int(
            len(document["content"]) / (settings.CHUNK_SIZE - settings.CHUNK_OVERLAP)
        )
        + 1
    )
    for chunk in new_indexed_document["_source"]["chunks"]:
        assert (
            chunk["embedding"]
            == albert_embedding_response.response["data"][0]["embedding"]
        )
        assert chunk["content"] in document["content"]
        assert len(chunk["content"]) < len(document["content"])


def test_api_documents_index_language_params():
    """language_code query param should control which language is indexed."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])

    new_indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )
    language_code = "en"
    assert (
        new_indexed_document["_source"][f"title.{language_code}"]
        == document["title"].strip().lower()
    )
    assert (
        new_indexed_document["_source"][f"content.{language_code}"]
        == document["content"]
    )
    other_language_code = "fr"
    # only the requested language is indexed
    assert not f"content.{other_language_code}" in new_indexed_document["_source"]


def test_api_documents_index_and_reindex_same_document():
    """
    Indexing the same document twice should update it.
    If the detected language changes the new language code should be used and the
    former language code should not be present anymore.
    """
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    # First indexing with unrecognized language title
    document["title"] = "planning"
    APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
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
    APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
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


def test_api_documents_index_single_hybrid_disabled_success():
    """If hybrid search is not enabled, the indexing should have an embedding equal to None."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()
    opensearch.check_hybrid_search_enabled.cache_clear()

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])

    new_indexed_document = opensearch.opensearch_client().get(
        index=service.index_name, id=str(document["id"])
    )
    assert new_indexed_document["_version"] == 1
    assert (
        new_indexed_document["_source"]["title.en"] == document["title"].strip().lower()
    )
    assert new_indexed_document["_source"]["content.en"] == document["content"]
    assert new_indexed_document["_source"]["chunks"] is None


def test_api_documents_index_single_ensure_index(settings):
    """A registered service should be created the opensearch index if needed."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()
    opensearch_client_ = opensearch.opensearch_client()

    with pytest.raises(NotFoundError):
        opensearch_client_.indices.get(index=service.index_name)

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["_id"] == str(document["id"])

    # The index has been rebuilt
    data = opensearch_client_.indices.get(index=service.index_name)

    assert data[service.index_name]["mappings"] == {
        "dynamic": "strict",
        "properties": {
            "chunks": {
                "type": "nested",
                "properties": {
                    "content": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": settings.EMBEDDING_DIMENSION,
                        "method": {
                            "engine": "lucene",
                            "space_type": "l2",
                            "name": "hnsw",
                            "parameters": {},
                        },
                    },
                    "index": {"type": "integer"},
                },
            },
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
            "embedding_model": {"type": "keyword"},
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

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert response.data[0]["msg"] == error_message
    assert response.data[0]["type"] == error_type


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

    response = APIClient().post(
        "/api/v1.0/documents/index/",
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
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    del document[field]

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
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

    response = APIClient().post(
        "/api/v1.0/documents/index/",
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
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    now = timezone.now()
    document[field] = now + datetime.timedelta(seconds=3)

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert response.data[0]["msg"] == f"Value error, {field:s} must be earlier than now"
    assert response.data[0]["type"] == "value_error"


def test_api_documents_index_empty_content_check():
    """Test document indexing with both empty title & content."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build()

    document["content"] = ""
    document["title"] = ""

    response = APIClient().post(
        "/api/v1.0/documents/index/",
        document,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )

    assert response.status_code == 400
    assert (
        response.data[0]["msg"]
        == "Value error, Either title or content should have at least 1 character"
    )
    assert response.data[0]["type"] == "value_error"
