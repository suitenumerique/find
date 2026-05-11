"""Tests for single-document deletion API endpoint."""

import pytest
import responses
from rest_framework.test import APIClient

from core import factories
from core.utils import prepare_index

from .utils import build_authorization_bearer, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


def test_api_resources_delete_anonymous():
    """Anonymous requests should not be allowed to delete documents."""
    response = APIClient().delete(
        "/api/v1.0/resources/00000000-0000-0000-0000-000000000001/",
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Authentication credentials were not provided."
    }


@responses.activate
def test_api_resources_delete_success(settings):
    """Authenticated users should be able to delete documents they have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(1, users=["user_sub"])
    prepare_index(service.index_name, documents, service)

    response = APIClient().delete(
        f"/api/v1.0/resources/{documents[0]['id']}/",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 204
    assert response.content == b""


@responses.activate
def test_api_resources_delete_not_found(settings):
    """Deleting a non-existent document should return 404."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    prepare_index(service.index_name, [], service)

    response = APIClient().delete(
        "/api/v1.0/resources/00000000-0000-0000-0000-000000000001/",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


@responses.activate
def test_api_resources_delete_forbidden(settings):
    """Users should not be able to delete documents they don't have access to."""
    setup_oicd_resource_server(responses, settings, sub="user_sub")

    service = factories.ServiceFactory()
    documents = factories.DocumentSchemaFactory.build_batch(1, users=["other_user"])
    prepare_index(service.index_name, documents, service)

    response = APIClient().delete(
        f"/api/v1.0/resources/{documents[0]['id']}/",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized to delete this document."}


def test_api_resources_delete_invalid_uuid_path():
    """Invalid UUID in path should return JSON 404."""
    response = APIClient().delete(
        "/api/v1.0/resources/invalid-uuid/",
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}
