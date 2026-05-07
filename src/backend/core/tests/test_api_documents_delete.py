"""Tests for deleting documents from OpenSearch over the API"""

import logging
from typing import List

import opensearchpy
import pytest
import responses
from opensearchpy.helpers import bulk
from rest_framework.test import APIClient

from core import factories
from core.services.indexing import ensure_index_exists, prepare_document_for_indexing
from core.services.opensearch import opensearch_client

from .utils import build_authorization_bearer, setup_oicd_resource_server

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

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


@responses.activate
def test_api_documents_delete_success(settings):
    """Authenticated users should be able to delete documents they have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    # Create documents user has access to
    documents = factories.DocumentFactory.build_batch(3, users=["user_sub"])
    prepare_index(settings.OPENSEARCH_INDEX, documents, service_name=service.name)
    document_to_delete_ids = [doc["id"] for doc in documents[:2]]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": document_to_delete_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in documents:
        if document["id"] in document_to_delete_ids:
            with pytest.raises(opensearchpy.exceptions.NotFoundError):
                opensearch_client_.get(
                    index=settings.OPENSEARCH_INDEX, id=document["id"]
                )
        else:
            doc = opensearch_client_.get(
                index=settings.OPENSEARCH_INDEX, id=document["id"]
            )
            assert doc["found"]


@responses.activate
def test_api_documents_delete_no_access(settings):
    """Users should not be able to delete documents they don't have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    # Create documents where user_sub does NOT have access
    documents = factories.DocumentFactory.build_batch(2, users=["other_sub"])
    prepare_index(settings.OPENSEARCH_INDEX, documents, service_name=service.name)

    document_ids = [doc["id"] for doc in documents]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": document_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 0,
        "undeleted-document-ids": document_ids,
    }

    # Verify documents not deleted
    opensearch_client_ = opensearch_client()
    for doc_id in document_ids:
        doc = opensearch_client_.get(index=settings.OPENSEARCH_INDEX, id=doc_id)
        assert doc["found"]


@responses.activate
def test_api_documents_delete_mixed_access(settings):
    """Deleting a mix of owned and non-owned documents should only delete owned ones."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    # Create documents with different access
    owned_documents = factories.DocumentFactory.build_batch(2, users=["user_sub"])
    other_documents = factories.DocumentFactory.build_batch(2, users=["other_user"])
    prepare_index(
        settings.OPENSEARCH_INDEX,
        owned_documents + other_documents,
        service_name=service.name,
    )

    owned_document_ids = [doc["id"] for doc in owned_documents]
    other_document_ids = [doc["id"] for doc in other_documents]
    non_existing_document_ids = ["non-existent-1", "non-existent-2"]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {
            "document_ids": owned_document_ids
            + other_document_ids
            + non_existing_document_ids,
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 2,
        "undeleted-document-ids": other_document_ids + non_existing_document_ids,
    }

    # Verify only owned documents are deleted
    opensearch_client_ = opensearch_client()
    for document_id in owned_document_ids:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=settings.OPENSEARCH_INDEX, id=document_id)

    for document_id in other_document_ids:
        document = opensearch_client_.get(
            index=settings.OPENSEARCH_INDEX, id=document_id
        )
        assert document["found"]


@responses.activate
def test_api_documents_delete_missing_document_ids_and_tags(settings):
    """Requests missing both document_ids and tags should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    prepare_index(settings.OPENSEARCH_INDEX, [], service_name=service.name)

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "value_error",
            "loc": [],
            "msg": "Value error, At least one of 'document_ids' or 'tags' must be provided",
        }
    ]


@responses.activate
def test_api_documents_delete_empty_document_ids(settings):
    """Requests with empty document_ids and no tags should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "value_error",
            "loc": [],
            "msg": "Value error, At least one of 'document_ids' or 'tags' must be provided",
        }
    ]


@responses.activate
def test_api_documents_delete_both_filters_empty(settings):
    """Requests with both document_ids and tags empty should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": [], "tags": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "value_error",
            "loc": [],
            "msg": "Value error, At least one of 'document_ids' or 'tags' must be provided",
        }
    ]


@responses.activate
def test_api_documents_delete_nonexistent_documents(settings):
    """
    Deleting non-existent documents should not raise an error
    and return the list of undeleted ids.
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    # Create index but with no documents
    prepare_index(settings.OPENSEARCH_INDEX, [], service_name=service.name)

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": ["non-existent-id"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 0,
        "undeleted-document-ids": ["non-existent-id"],
    }


@responses.activate
@pytest.mark.flaky(
    reruns=2, reason="OpenSearch index race condition under high parallelism"
)
def test_api_documents_delete_by_single_tag(settings):
    """Users should be able to delete documents by tags."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
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
        factories.DocumentFactory.build(users=["other_user_sub"], tags=["delete-tag"]),
    ]
    prepare_index(
        settings.OPENSEARCH_INDEX,
        document_to_deletes + document_to_keep,
        service_name=service.name,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"tags": ["delete-tag"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in document_to_deletes:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=settings.OPENSEARCH_INDEX, id=document["id"])

    for document in document_to_keep:
        doc = opensearch_client_.get(index=settings.OPENSEARCH_INDEX, id=document["id"])
        assert doc["found"]


@responses.activate
def test_api_documents_delete_by_multiple_tags(settings):
    """Users should be able to delete documents matching any of multiple tags."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
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
        factories.DocumentFactory.build(
            users=["other_user_sub"], tags=["delete-tag-1"]
        ),
    ]
    prepare_index(
        settings.OPENSEARCH_INDEX,
        document_to_deletes + document_to_keep,
        service_name=service.name,
    )

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"tags": ["delete-tag-1", "delete-tag-2"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 3, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in document_to_deletes:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=settings.OPENSEARCH_INDEX, id=document["id"])

    for document in document_to_keep:
        doc = opensearch_client_.get(index=settings.OPENSEARCH_INDEX, id=document["id"])
        assert doc["found"]


@responses.activate
def test_api_documents_delete_by_ids_and_tags(settings):
    """Users should be able to delete documents by both IDs and tags (AND logic)."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
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

    prepare_index(
        settings.OPENSEARCH_INDEX,
        [
            document_delete_by_tag_and_id,
            document_delete_by_tag_keep_by_id,
            document_keep_by_tag_delete_by_id,
        ],
        service_name=service.name,
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
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "nb-deleted-documents": 1,
        "undeleted-document-ids": [document_keep_by_tag_delete_by_id["id"]],
    }

    opensearch_client_ = opensearch_client()
    with pytest.raises(opensearchpy.exceptions.NotFoundError):
        opensearch_client_.get(
            index=settings.OPENSEARCH_INDEX, id=document_delete_by_tag_and_id["id"]
        )

    doc = opensearch_client_.get(
        index=settings.OPENSEARCH_INDEX, id=document_delete_by_tag_keep_by_id["id"]
    )
    assert doc["found"]
