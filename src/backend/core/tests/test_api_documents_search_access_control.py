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
