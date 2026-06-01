"""Authentication contract tests for the /index/ endpoint.

These tests lock in the rule that only registered services can index documents:
/index/ is wired to ServiceTokenAuthentication, not ResourceServerAuthentication.
"""

import pytest
from rest_framework.test import APIClient

from .utils import build_authorization_bearer

pytestmark = pytest.mark.django_db


def test_api_documents_index_oidc_token_rejected():
    """OIDC-style bearer tokens must not be accepted by /index/."""
    response = APIClient().post(
        "/api/v1.0/documents/index/",
        [],
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid token."}
