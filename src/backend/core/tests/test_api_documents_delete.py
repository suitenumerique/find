"""Tests for deleting documents from OpenSearch over the API"""

import logging
from typing import List

import opensearchpy
import pytest
from opensearchpy.helpers import bulk
from rest_framework.test import APIClient

from core import factories
from core.services.indexing import ensure_index_exists, prepare_document_for_indexing
from core.services.opensearch import opensearch_client

from .utils import build_authorization_bearer

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.django_db


def prepare_index(
    index_name: str, documents: List[dict], service_name: str = "test-service"
):
    """Prepare the search index before testing a query on it.

    Args:
        index_name: The OpenSearch index name.
        documents: List of documents to index.
        service_name: Service name to assign to documents.
    """
    logger.info("Preparing index %s with %d documents", index_name, len(documents))

    client = opensearch_client()
    ensure_index_exists(index_name)
    if documents:
        actions = [
            {
                "_op_type": "index",
                "_index": index_name,
                "_id": document["id"],
                "_source": prepare_document_for_indexing(document, service_name),
            }
            for document in documents
        ]
        bulk(client, actions)
    client.indices.refresh(index=index_name)


def test_api_documents_delete_anonymous():
    """Anonymous requests should not be allowed to delete documents."""
    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": ["doc1"]},
        format="json",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


def test_api_documents_delete_oidc_token_rejected():
    """OIDC-style bearer tokens should not be allowed to delete documents."""
    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": ["doc1"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}


def test_api_documents_delete_success(settings):
    """Authenticated services should delete documents from their own index."""

    service = factories.ServiceFactory()
    documents = factories.DocumentFactory.build_batch(3, users=["user_sub"])
    service_index = f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}"
    prepare_index(service_index, documents, service_name=service.slug)
    document_to_delete_ids = [doc["id"] for doc in documents[:2]]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": document_to_delete_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in documents:
        if document["id"] in document_to_delete_ids:
            with pytest.raises(opensearchpy.exceptions.NotFoundError):
                opensearch_client_.get(index=service_index, id=document["id"])
        else:
            doc = opensearch_client_.get(index=service_index, id=document["id"])
            assert doc["found"]


def test_api_documents_delete_other_service_index_untouched(settings):
    """A service token should not delete documents from another service index."""
    service = factories.ServiceFactory()
    other_service = factories.ServiceFactory()
    documents = factories.DocumentFactory.build_batch(2)
    other_service_index = f"{settings.OPENSEARCH_INDEX_PREFIX}-{other_service.slug}"
    prepare_index(other_service_index, documents, service_name=other_service.slug)

    document_ids = [doc["id"] for doc in documents]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": document_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 0,
        "undeleted-document-ids": document_ids,
    }

    opensearch_client_ = opensearch_client()
    for doc_id in document_ids:
        doc = opensearch_client_.get(index=other_service_index, id=doc_id)
        assert doc["found"]


def test_api_documents_delete_mixed_existing_and_missing_ids(settings):
    """Deleting a mix of existing and missing IDs should report only missing IDs."""

    service = factories.ServiceFactory()
    documents = factories.DocumentFactory.build_batch(4)
    service_index = f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}"
    prepare_index(service_index, documents, service_name=service.slug)

    existing_document_ids = [doc["id"] for doc in documents]
    non_existing_document_ids = ["non-existent-1", "non-existent-2"]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": existing_document_ids + non_existing_document_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 4,
        "undeleted-document-ids": non_existing_document_ids,
    }

    opensearch_client_ = opensearch_client()
    for document_id in existing_document_ids:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=service_index, id=document_id)


def test_api_documents_delete_missing_document_ids_and_tags(settings):
    """Requests missing both document_ids and tags should return 400."""
    service = factories.ServiceFactory()
    prepare_index(
        f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}",
        [],
        service_name=service.slug,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "value_error",
            "loc": [],
            "msg": "Value error, At least one of 'document_ids' or 'tags' must be provided",
        }
    ]


def test_api_documents_delete_empty_document_ids():
    """Requests with empty document_ids and no tags should return 400."""
    service = factories.ServiceFactory()

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "value_error",
            "loc": [],
            "msg": "Value error, At least one of 'document_ids' or 'tags' must be provided",
        }
    ]


def test_api_documents_delete_both_filters_empty():
    """Requests with both document_ids and tags empty should return 400."""
    service = factories.ServiceFactory()

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": [], "tags": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "value_error",
            "loc": [],
            "msg": "Value error, At least one of 'document_ids' or 'tags' must be provided",
        }
    ]


def test_api_documents_delete_nonexistent_documents(settings):
    """
    Deleting non-existent documents should not raise an error
    and return the list of undeleted ids.
    """
    service = factories.ServiceFactory()
    # Create index but with no documents
    prepare_index(
        f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}",
        [],
        service_name=service.slug,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": ["non-existent-id"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 0,
        "undeleted-document-ids": ["non-existent-id"],
    }


@pytest.mark.flaky(
    reruns=2, reason="OpenSearch index race condition under high parallelism"
)
def test_api_documents_delete_by_single_tag(settings):
    """Services should be able to delete documents by tags."""
    service = factories.ServiceFactory()

    document_to_deletes = [
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag", "keep-tag-1"]
        ),
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag", "keep-tag-2"]
        ),
    ]
    document_to_keep = [
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["keep-tag-1", "keep-tag-2"]
        ),
        factories.DocumentFactory.build(users=["user_sub"], tags=["keep-tag-1"]),
        factories.DocumentFactory.build(users=["other_user_sub"], tags=["keep-tag-3"]),
    ]
    service_index = f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}"
    prepare_index(
        service_index,
        document_to_deletes + document_to_keep,
        service_name=service.slug,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"tags": ["delete-tag"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in document_to_deletes:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=service_index, id=document["id"])

    for document in document_to_keep:
        doc = opensearch_client_.get(index=service_index, id=document["id"])
        assert doc["found"]


def test_api_documents_delete_by_multiple_tags(settings):
    """Services should be able to delete documents matching any of multiple tags."""
    service = factories.ServiceFactory()

    document_to_deletes = [
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag-1", "keep-tag-1"]
        ),
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag-1", "delete-tag-2"]
        ),
        factories.DocumentFactory.build(users=["user_sub"], tags=["delete-tag-2"]),
    ]
    document_to_keep = [
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["keep-tag-1", "keep-tag-2"]
        ),
        factories.DocumentFactory.build(users=["user_sub"], tags=["keep-tag-1"]),
        factories.DocumentFactory.build(users=["other_user_sub"], tags=["keep-tag-3"]),
    ]
    service_index = f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}"
    prepare_index(
        service_index,
        document_to_deletes + document_to_keep,
        service_name=service.slug,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"tags": ["delete-tag-1", "delete-tag-2"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 3, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in document_to_deletes:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=service_index, id=document["id"])

    for document in document_to_keep:
        doc = opensearch_client_.get(index=service_index, id=document["id"])
        assert doc["found"]


def test_api_documents_delete_by_ids_and_tags(settings):
    """Services should be able to delete documents by both IDs and tags (AND logic)."""
    service = factories.ServiceFactory()

    document_delete_by_tag_and_id = factories.DocumentFactory.build(
        users=["user_sub"], tags=["delete-tag"]
    )
    document_delete_by_tag_keep_by_id = factories.DocumentFactory.build(
        users=["user_sub"], tags=["delete-tag"]
    )
    document_keep_by_tag_delete_by_id = factories.DocumentFactory.build(
        users=["user_sub"]
    )

    service_index = f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}"
    prepare_index(
        service_index,
        [
            document_delete_by_tag_and_id,
            document_delete_by_tag_keep_by_id,
            document_keep_by_tag_delete_by_id,
        ],
        service_name=service.slug,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {
            "document_ids": [
                document_delete_by_tag_and_id["id"],
                document_keep_by_tag_delete_by_id["id"],
            ],
            "tags": ["delete-tag"],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 1,
        "undeleted-document-ids": [document_keep_by_tag_delete_by_id["id"]],
    }

    opensearch_client_ = opensearch_client()
    with pytest.raises(opensearchpy.exceptions.NotFoundError):
        opensearch_client_.get(
            index=service_index, id=document_delete_by_tag_and_id["id"]
        )

    doc = opensearch_client_.get(
        index=service_index, id=document_delete_by_tag_keep_by_id["id"]
    )
    assert doc["found"]


def test_api_documents_delete_by_tag_more_than_default_search_size(settings):
    """Tag-only deletion should not be capped by OpenSearch's default 10 search hits."""
    service = factories.ServiceFactory()
    document_to_deletes = factories.DocumentFactory.build_batch(
        12, users=["user_sub"], tags=["delete-tag"]
    )
    document_to_keep = factories.DocumentFactory.build_batch(
        2, users=["user_sub"], tags=["keep-tag"]
    )
    service_index = f"{settings.OPENSEARCH_INDEX_PREFIX}-{service.slug}"
    prepare_index(
        service_index,
        document_to_deletes + document_to_keep,
        service_name=service.slug,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"tags": ["delete-tag"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 12, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in document_to_deletes:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=service_index, id=document["id"])

    for document in document_to_keep:
        doc = opensearch_client_.get(index=service_index, id=document["id"])
        assert doc["found"]
