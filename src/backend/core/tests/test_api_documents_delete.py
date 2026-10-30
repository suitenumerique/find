"""Tests for deleting documents from OpenSearch over the API"""

from django.test import Client

import opensearchpy
import pytest
import responses

from core import factories
from core.services.opensearch import opensearch_client
from core.utils import prepare_index

from .utils import build_authorization_bearer, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


def test_api_documents_delete_anonymous():
    """Anonymous requests should not be allowed to delete documents."""
    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": "service-name", "document_ids": ["doc1"]},
        content_type="application/json",
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


@responses.activate
def test_api_documents_delete_wrong_service_name(settings):
    """Requests with a wrong service name should return 400 Bad Request."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": "wrong-service", "document_ids": ["0"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request."}


@responses.activate
def test_api_documents_delete_success(settings):
    """Authenticated users should be able to delete documents they have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    # Create documents user has access to
    documents = factories.DocumentSchemaFactory.build_batch(3, users=["user_sub"])
    prepare_index(service.index_name, documents)
    document_to_delete_ids = [doc["id"] for doc in documents[:2]]

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": document_to_delete_ids},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}

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

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": document_ids},
        content_type="application/json",
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
        doc = opensearch_client_.get(index=service.index_name, id=doc_id)
        assert doc["found"]


@responses.activate
def test_api_documents_delete_mixed_access(settings):
    """Deleting a mix of owned and non-owned documents should only delete owned ones."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    # Create documents with different access
    owned_documents = factories.DocumentSchemaFactory.build_batch(2, users=["user_sub"])
    other_documents = factories.DocumentSchemaFactory.build_batch(
        2, users=["other_user"]
    )
    prepare_index(service.index_name, owned_documents + other_documents)

    owned_document_ids = [doc["id"] for doc in owned_documents]
    other_document_ids = [doc["id"] for doc in other_documents]
    non_existing_document_ids = ["non-existent-1", "non-existent-2"]

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {
            "service": service.name,
            "document_ids": owned_document_ids
            + other_document_ids
            + non_existing_document_ids,
        },
        content_type="application/json",
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
            opensearch_client_.get(index=service.index_name, id=document_id)

    for document_id in other_document_ids:
        document = opensearch_client_.get(index=service.index_name, id=document_id)
        assert document["found"]


@responses.activate
def test_api_documents_delete_missing_document_ids_and_tags(settings):
    """Requests missing both document_ids and tags should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name},
        content_type="application/json",
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
    service = factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": []},
        content_type="application/json",
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
    service = factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": [], "tags": []},
        content_type="application/json",
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
def test_api_documents_delete_missing_service(settings):
    """Requests missing the service field should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": ["doc1"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {"type": "missing", "loc": ["service"], "msg": "Field required"}
    ]


@responses.activate
def test_api_documents_delete_too_many_document_ids(settings):
    """Requests with more than 1000 document ids should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": [str(i) for i in range(1001)]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == [
        {
            "type": "too_long",
            "loc": ["document_ids"],
            "msg": "List should have at most 1000 items after validation, not 1001",
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
    prepare_index(service.index_name, [])

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "document_ids": ["non-existent-id"]},
        content_type="application/json",
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
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["delete-tag", "keep-tag-1"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["delete-tag", "keep-tag-2"]
        ),
    ]
    document_to_keep = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["keep-tag-1", "keep-tag-2"]
        ),
        factories.DocumentSchemaFactory.build(users=["user_sub"], tags=["keep-tag-1"]),
        factories.DocumentSchemaFactory.build(
            users=["other_user_sub"], tags=["delete-tag"]
        ),
    ]
    prepare_index(service.index_name, document_to_deletes + document_to_keep)

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "tags": ["delete-tag"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in document_to_deletes:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=service.index_name, id=document["id"])

    for document in document_to_keep:
        doc = opensearch_client_.get(index=service.index_name, id=document["id"])
        assert doc["found"]


@responses.activate
def test_api_documents_delete_by_multiple_tags(settings):
    """Users should be able to delete documents matching any of multiple tags."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    document_to_deletes = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["delete-tag-1", "keep-tag-1"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["delete-tag-1", "delete-tag-2"]
        ),
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["delete-tag-2"]
        ),
    ]
    document_to_keep = [
        factories.DocumentSchemaFactory.build(
            users=["user_sub"], tags=["keep-tag-1", "keep-tag-2"]
        ),
        factories.DocumentSchemaFactory.build(users=["user_sub"], tags=["keep-tag-1"]),
        factories.DocumentSchemaFactory.build(
            users=["other_user_sub"], tags=["delete-tag-1"]
        ),
    ]
    prepare_index(service.index_name, document_to_deletes + document_to_keep)

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "tags": ["delete-tag-1", "delete-tag-2"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 3, "undeleted-document-ids": []}

    opensearch_client_ = opensearch_client()
    for document in document_to_deletes:
        with pytest.raises(opensearchpy.exceptions.NotFoundError):
            opensearch_client_.get(index=service.index_name, id=document["id"])

    for document in document_to_keep:
        doc = opensearch_client_.get(index=service.index_name, id=document["id"])
        assert doc["found"]


@responses.activate
def test_api_documents_delete_by_ids_and_tags(settings):
    """Users should be able to delete documents by both IDs and tags (AND logic)."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    document_delete_by_tag_and_id = factories.DocumentSchemaFactory.build(
        users=["user_sub"], tags=["delete-tag"]
    )
    document_delete_by_tag_keep_by_id = factories.DocumentSchemaFactory.build(
        users=["user_sub"], tags=["delete-tag"]
    )
    document_keep_by_tag_delete_by_id = factories.DocumentSchemaFactory.build(
        users=["user_sub"]
    )

    prepare_index(
        service.index_name,
        [
            document_delete_by_tag_and_id,
            document_delete_by_tag_keep_by_id,
            document_keep_by_tag_delete_by_id,
        ],
    )

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {
            "service": service.name,
            "document_ids": [
                document_delete_by_tag_and_id["id"],
                document_keep_by_tag_delete_by_id["id"],
            ],
            "tags": ["delete-tag"],
        },
        content_type="application/json",
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
            index=service.index_name, id=document_delete_by_tag_and_id["id"]
        )

    doc = opensearch_client_.get(
        index=service.index_name, id=document_delete_by_tag_keep_by_id["id"]
    )
    assert doc["found"]


@pytest.mark.xfail(
    strict=True,
    reason="#173: delete may target the wrong index when a service has sub-services",
)
@responses.activate
def test_api_documents_delete_service_with_sub_services(settings):
    """Deletion should target the index of the requested service."""
    setup_oicd_resource_server(responses, settings, sub="user_sub", audience="c-client")

    service_a = factories.ServiceFactory(name="test-index-a", client_id="a-client")
    service_c = factories.ServiceFactory(name="test-index-c", client_id="c-client")
    service_c.services.set([service_a])

    documents = {}
    for service in [service_a, service_c]:
        documents[service.name] = factories.DocumentSchemaFactory.build(
            users=["user_sub"]
        )
        prepare_index(service.index_name, [documents[service.name]])

    # The wrong index is picked for one of the two services, whatever the set order
    for service in [service_a, service_c]:
        document = documents[service.name]
        response = Client().post(
            "/api/v1.0/documents/delete/",
            {"service": service.name, "document_ids": [document["id"]]},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
        )

        assert response.status_code == 200
        assert response.json() == {
            "nb-deleted-documents": 1,
            "undeleted-document-ids": [],
        }


@responses.activate
def test_api_documents_delete_more_than_ten_documents(settings):
    """All the matching documents should be deleted, not only the first 10."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    service = factories.ServiceFactory()

    documents = factories.DocumentSchemaFactory.build_batch(
        11, users=["user_sub"], tags=["delete-tag"]
    )
    prepare_index(service.index_name, documents)

    response = Client().post(
        "/api/v1.0/documents/delete/",
        {"service": service.name, "tags": ["delete-tag"]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 11, "undeleted-document-ids": []}
