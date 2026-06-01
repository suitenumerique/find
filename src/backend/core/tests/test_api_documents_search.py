"""Authentication contract tests for the /search/ endpoint.

These tests lock in the rule that services cannot search: /search/ is wired to
ResourceServerAuthentication (OIDC users only), not ServiceTokenAuthentication.
A valid Service.token accepted by /index/ and /delete/ must be rejected here.
"""

import json

import pytest
import responses as responses_lib
from rest_framework.test import APIClient

from core import factories

from .utils import setup_oicd_resource_server

pytestmark = pytest.mark.django_db


@responses_lib.activate
def test_api_documents_search_service_token_rejected(settings):
    """Service bearer tokens must not be accepted by /search/."""
    setup_oicd_resource_server(
        responses_lib,
        settings,
        introspect=lambda request, user_info: (
            200,
            {},
            json.dumps({"active": False}),
        ),
    )
    service = factories.ServiceFactory()

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "anything"},
        HTTP_AUTHORIZATION=f"Bearer {service.token}",
        format="json",
    )

    assert response.status_code in (400, 401, 403)


@responses_lib.activate
def test_api_documents_search_anonymous_rejected(settings):
    """Anonymous requests (no Authorization header) must be rejected by /search/."""
    setup_oicd_resource_server(responses_lib, settings)

    response = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "anything"},
        format="json",
    )

    assert response.status_code in (400, 401, 403)
