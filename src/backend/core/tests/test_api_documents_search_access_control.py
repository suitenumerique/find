"""
Test suite for access control when searching documents over the API.

Don't use pytest parametrized tests because batch generation and indexing
of documents is slow and better done only once.
"""

import pytest
from rest_framework.test import APIClient

from core import enums, factories

from .utils import prepare_index

pytestmark = pytest.mark.django_db


def test_api_documents_search_access_control_anonymous():
    """Anonymous users should not be allowed to search documents even public."""
    service = factories.ServiceFactory(name="test-service")
    documents = []
    for reach in enums.ReachEnum:
        documents.extend(factories.DocumentSchemaFactory.build_batch(3, reach=reach))
    prepare_index(service.name, documents)

    response = APIClient().post("/api/v1.0/documents/search/?q=*")

    assert response.status_code == 403


def test_api_documents_search_access_control():
    """
    Authenticated users should only see documents:
    - for which they are listed in the "users" field
    - that have a reach set to "authenticated" or "public"
    (groups is not yet implemnted)
    """
    service = factories.ServiceFactory(name="test-service")
    documents_reach = factories.DocumentSchemaFactory.build_batch(6)
    documents_open = [
        doc for doc in documents_reach if doc["reach"] in ["authenticated", "public"]
    ]
    documents_user = factories.DocumentSchemaFactory.build_batch(
        6, users=["123456", "654321"]
    )
    expected_ids = [doc["id"] for doc in documents_open + documents_user]

    prepare_index(service.name, documents_user + documents_reach)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION="Bearer 123456",
    )

    assert response.status_code == 200
    for result in response.json():
        assert result["_id"] in expected_ids
