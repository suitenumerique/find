"""Tests for deleting documents from OpenSearch over the API"""

import opensearchpy
import pytest
import responses
from rest_framework.test import APIClient

from core import factories
from core.services.opensearch import opensearch_client
from core.utils import prepare_index

from .utils import build_authorization_bearer, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


def test_api_documents_delete_anonymous():
    """Anonymous requests should not be allowed to delete documents."""
    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"service": "service-name", "document_ids": ["doc1"]},
        format="json",
    )

    assert response.status_code == 401


@responses.activate
def test_api_documents_delete_wrong_service_name(settings):
    """Requests with a wrong service name should return 400 Bad Request."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"service": "wrong-service", "document_ids": ["0"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == 'Invalid request.'


@responses.activate
def test_api_documents_delete_success(settings):
    """Authenticated users should be able to delete documents they have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    # Create documents user has access to
    documents = factories.DocumentSchemaFactory.build_batch(3, users=["user_sub"])
    prepare_index(service.index_name, documents)
    document_to_delete_ids = [doc["id"] for doc in documents[:2]]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": document_to_delete_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json()["nb-deleted-documents"] == 2

    opensearch_client_ = opensearch_client()
    for document in documents:
        if document["id"] in document_to_delete_ids:
            with pytest.raises(opensearchpy.exceptions.NotFoundError):
                opensearch_client_.get(index=service.index_name, id=document["id"])
        else:
            doc = opensearch_client_.get(index=service.index_name, id=document["id"])
            assert doc["found"]


@responses.activate
def test_api_documents_delete_no_access(settings):
    """Users should not be able to delete documents they don't have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    # Create documents where user_sub does NOT have access
    documents = factories.DocumentSchemaFactory.build_batch(2, users=["other_sub"])
    prepare_index(service.index_name, documents)

    document_ids = [doc["id"] for doc in documents]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": document_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json()["nb-deleted-documents"] == 0

    # Verify documents not deleted
    opensearch_client_ = opensearch_client()
    for doc_id in document_ids:
        doc = opensearch_client_.get(index=service.index_name, id=doc_id)
        assert doc["found"]


@responses.activate
def test_api_documents_delete_mixed_access(settings):
    """Deleting a mix of owned and non-owned documents should only delete owned ones."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    # Create documents with different access
    owned_docs = factories.DocumentSchemaFactory.build_batch(2, users=["user_sub"])
    other_docs = factories.DocumentSchemaFactory.build_batch(2, users=["other_user"])
    prepare_index(service.index_name, owned_docs + other_docs)

    document_ids = [doc["id"] for doc in owned_docs + other_docs]

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": document_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json()["nb-deleted-documents"] == 2

    # Verify only owned documents are deleted
    opensearch_client_ = opensearch_client()
    for doc_id in [d["id"] for d in owned_docs]:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=service.index_name, id=doc_id)

    for doc_id in [d["id"] for d in other_docs]:
        doc = opensearch_client_.get(index=service.index_name, id=doc_id)
        assert doc["found"]


@responses.activate
def test_api_documents_delete_invalid_params(settings):
    """Requests with invalid parameters should return 400 Bad Request."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    # Missing document_ids
    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {
            "service": service.name,
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400

    # Empty document_ids
    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400

    # Missing service
    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": ["doc1"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400


@responses.activate
def test_api_documents_delete_nonexistent_documents(settings):
    """Deleting non-existent documents should not raise an error and do nothing."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()
    # Create index but with no documents
    prepare_index(service.index_name, [])

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": ["non-existent-id"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json()["nb-deleted-documents"] == 0
