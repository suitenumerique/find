"""Tests for deleting documents from OpenSearch over the API (unit tests with mocked OpenSearch)"""

from unittest.mock import MagicMock

from django.conf import LazySettings

import pytest
import responses
from rest_framework.test import APIClient

from core import factories
from core.views import DeleteDocumentsView

from ...utils import build_authorization_bearer, setup_oicd_resource_server
from ...utils_opensearch import mock_search_response

pytestmark = pytest.mark.django_db


def test_api_documents_delete_anonymous():
    """Anonymous requests should not be allowed to delete documents."""
    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": ["doc1"]},
        format="json",
    )

    assert response.status_code == 401
    assert response.json() == {
        "type": "about:blank",
        "title": "Unauthorized",
        "status": 401,
        "detail": "Authentication credentials were not provided.",
    }


@responses.activate
def test_api_documents_delete_success(
    settings: LazySettings, mock_opensearch_client: MagicMock
) -> None:
    """Authenticated users should be able to delete documents they have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    factories.ServiceFactory()
    # Create documents user has access to
    documents = factories.DocumentFactory.build_batch(3, users=["user_sub"])
    document_to_delete_ids = [doc["id"] for doc in documents[:2]]

    # Configure mock to return documents when searched
    mock_opensearch_client.search.return_value = mock_search_response(
        hits=[
            {"_id": doc["id"], "_source": {"users": ["user_sub"]}}
            for doc in documents[:2]
        ],
        total=2,
    )
    mock_opensearch_client.delete_by_query.return_value = {"deleted": 2}

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": document_to_delete_ids},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}


@responses.activate
def test_api_documents_delete_no_access(
    settings: LazySettings, mock_opensearch_client: MagicMock
) -> None:
    """Users should not be able to delete documents they don't have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()
    # Create documents where user_sub does NOT have access
    documents = factories.DocumentFactory.build_batch(2, users=["other_sub"])

    document_ids = [doc["id"] for doc in documents]

    # Configure mock to return no documents (user has no access)
    mock_opensearch_client.search.return_value = mock_search_response(hits=[], total=0)

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


@responses.activate
def test_api_documents_delete_mixed_access(
    settings: LazySettings, mock_opensearch_client: MagicMock
) -> None:
    """Deleting a mix of owned and non-owned documents should only delete owned ones."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    factories.ServiceFactory()
    # Create documents with different access
    owned_documents = factories.DocumentFactory.build_batch(2, users=["user_sub"])
    other_documents = factories.DocumentFactory.build_batch(2, users=["other_user"])

    owned_document_ids = [doc["id"] for doc in owned_documents]
    other_document_ids = [doc["id"] for doc in other_documents]
    non_existing_document_ids = ["non-existent-1", "non-existent-2"]

    # Configure mock to return only owned documents
    mock_opensearch_client.search.return_value = mock_search_response(
        hits=[
            {"_id": doc["id"], "_source": {"users": ["user_sub"]}}
            for doc in owned_documents
        ],
        total=2,
    )
    mock_opensearch_client.delete_by_query.return_value = {"deleted": 2}

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


@responses.activate
def test_api_documents_delete_missing_document_ids_and_tags(
    settings: LazySettings,
    mock_opensearch_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Requests missing both document_ids and tags should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "detail": "Validation failed",
    }


@responses.activate
def test_api_documents_delete_empty_document_ids(
    settings: LazySettings,
    mock_opensearch_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Requests with empty document_ids and no tags should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "detail": "Validation failed",
    }


@responses.activate
def test_api_documents_delete_both_filters_empty(
    settings: LazySettings,
    mock_opensearch_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Requests with both document_ids and tags empty should return 400."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": [], "tags": []},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 400
    assert response.json() == {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "detail": "Validation failed",
    }


@responses.activate
def test_api_documents_delete_nonexistent_documents(
    settings: LazySettings, mock_opensearch_client: MagicMock
) -> None:
    """
    Deleting non-existent documents should not raise an error
    and return the list of undeleted ids.
    """
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    # Configure mock to return no documents
    mock_opensearch_client.search.return_value = mock_search_response(hits=[], total=0)

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
def test_api_documents_delete_by_single_tag(
    settings: LazySettings, mock_opensearch_client: MagicMock
) -> None:
    """Users should be able to delete documents by tags."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    document_to_deletes = [
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag", "keep-tag-1"]
        ),
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag", "keep-tag-2"]
        ),
    ]

    # Configure mock to return documents matching the tag
    mock_opensearch_client.search.return_value = mock_search_response(
        hits=[
            {"_id": doc["id"], "_source": {"users": ["user_sub"], "tags": doc["tags"]}}
            for doc in document_to_deletes
        ],
        total=2,
    )
    mock_opensearch_client.delete_by_query.return_value = {"deleted": 2}

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"tags": ["delete-tag"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 2, "undeleted-document-ids": []}


@responses.activate
def test_api_documents_delete_by_multiple_tags(
    settings: LazySettings, mock_opensearch_client: MagicMock
) -> None:
    """Users should be able to delete documents matching any of multiple tags."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    document_to_deletes = [
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag-1", "keep-tag-1"]
        ),
        factories.DocumentFactory.build(
            users=["user_sub"], tags=["delete-tag-1", "delete-tag-2"]
        ),
        factories.DocumentFactory.build(users=["user_sub"], tags=["delete-tag-2"]),
    ]

    # Configure mock to return documents matching the tags
    mock_opensearch_client.search.return_value = mock_search_response(
        hits=[
            {"_id": doc["id"], "_source": {"users": ["user_sub"], "tags": doc["tags"]}}
            for doc in document_to_deletes
        ],
        total=3,
    )
    mock_opensearch_client.delete_by_query.return_value = {"deleted": 3}

    response = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"tags": ["delete-tag-1", "delete-tag-2"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 200
    assert response.json() == {"nb-deleted-documents": 3, "undeleted-document-ids": []}


@responses.activate
def test_api_documents_delete_by_ids_and_tags(
    settings: LazySettings, mock_opensearch_client: MagicMock
) -> None:
    """Users should be able to delete documents by both IDs and tags (AND logic)."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")
    factories.ServiceFactory()

    document_delete_by_tag_and_id = factories.DocumentFactory.build(
        users=["user_sub"], tags=["delete-tag"]
    )
    # This document exists but won't be in the delete request's document_ids
    factories.DocumentFactory.build(users=["user_sub"], tags=["delete-tag"])
    document_keep_by_tag_delete_by_id = factories.DocumentFactory.build(
        users=["user_sub"]
    )

    # Configure mock to return only the document that matches both ID and tag
    mock_opensearch_client.search.return_value = mock_search_response(
        hits=[
            {
                "_id": document_delete_by_tag_and_id["id"],
                "_source": {"users": ["user_sub"], "tags": ["delete-tag"]},
            }
        ],
        total=1,
    )
    mock_opensearch_client.delete_by_query.return_value = {"deleted": 1}

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


# pylint: disable=protected-access
class TestBuildQuery:
    """Unit tests for DeleteDocumentsView._build_query() method."""

    def test_build_query_user_only(self):
        assert DeleteDocumentsView()._build_query(user_sub="test-user") == {
            "bool": {"must": [{"term": {"users": "test-user"}}]}
        }

    def test_build_query_with_document_ids(self):
        assert DeleteDocumentsView()._build_query(
            user_sub="test-user", document_ids=["doc1", "doc2"]
        ) == {
            "bool": {
                "must": [
                    {"term": {"users": "test-user"}},
                    {"ids": {"values": ["doc1", "doc2"]}},
                ]
            }
        }

    def test_build_query_with_tags(self):
        assert DeleteDocumentsView()._build_query(
            user_sub="test-user", tags=["tag1", "tag2"]
        ) == {
            "bool": {
                "must": [
                    {"term": {"users": "test-user"}},
                    {"terms": {"tags": ["tag1", "tag2"]}},
                ]
            }
        }

    def test_build_query_with_document_ids_and_tags(self):
        assert DeleteDocumentsView()._build_query(
            user_sub="test-user", document_ids=["doc1", "doc2"], tags=["tag1", "tag2"]
        ) == {
            "bool": {
                "must": [
                    {"term": {"users": "test-user"}},
                    {"ids": {"values": ["doc1", "doc2"]}},
                    {"terms": {"tags": ["tag1", "tag2"]}},
                ]
            }
        }

    def test_build_query_with_empty_document_ids(self):
        assert DeleteDocumentsView()._build_query(
            user_sub="test-user", document_ids=[]
        ) == {"bool": {"must": [{"term": {"users": "test-user"}}]}}

    def test_build_query_with_empty_tags(self):
        assert DeleteDocumentsView()._build_query(
            user_sub="test-user", tags=[]
        ) == {"bool": {"must": [{"term": {"users": "test-user"}}]}}

    def test_build_query_with_single_document_id(self):
        assert DeleteDocumentsView()._build_query(
            user_sub="test-user", document_ids=["single-doc"]
        ) == {
            "bool": {
                "must": [
                    {"term": {"users": "test-user"}},
                    {"ids": {"values": ["single-doc"]}},
                ]
            }
        }

    def test_build_query_with_single_tag(self):
        assert DeleteDocumentsView()._build_query(
            user_sub="test-user", tags=["single-tag"]
        ) == {
            "bool": {
                "must": [
                    {"term": {"users": "test-user"}},
                    {"terms": {"tags": ["single-tag"]}},
                ]
            }
        }
