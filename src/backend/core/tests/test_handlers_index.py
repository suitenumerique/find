from datetime import timedelta
from unittest.mock import MagicMock

from django.utils import timezone

import pytest
from django_bolt.testing import TestClient

pytestmark = pytest.mark.django_db(transaction=True)

TEST_DOC_ID = "2d2f4501-aafc-49dd-9d81-401c181f9068"


@pytest.fixture
def valid_document_payload() -> dict:
    return {
        "id": TEST_DOC_ID,
        "title": "Test Document",
        "content": "Test content for indexing",
        "depth": 0,
        "path": "/test",
        "numchild": 0,
        "created_at": "2020-01-01T00:00:00+00:00",
        "updated_at": "2020-01-02T00:00:00+00:00",
        "size": 100,
        "is_active": True,
        "users": [],
        "groups": [],
        "tags": [],
    }


class TestIndexDocumentView:
    @pytest.mark.vcr
    def test_index_valid_document_returns_201(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    def test_index_missing_auth_returns_401(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Service authentication required"}
        mock_opensearch_client.index.assert_not_called()

    def test_index_invalid_token_returns_401(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer invalid-token-that-does-not-exist"},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Service authentication required"}
        mock_opensearch_client.index.assert_not_called()

    def test_index_missing_required_field_id_returns_422(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        del valid_document_payload["id"]

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "id"],
                    "msg": "Object missing required field `id`",
                    "type": "missing_field",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_missing_required_field_title_returns_422(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        del valid_document_payload["title"]

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "title"],
                    "msg": "Object missing required field `title`",
                    "type": "missing_field",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_missing_required_field_content_returns_422(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        del valid_document_payload["content"]

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "content"],
                    "msg": "Object missing required field `content`",
                    "type": "missing_field",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_invalid_uuid_returns_422(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["id"] = "not-a-valid-uuid"

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "id"],
                    "msg": "Invalid UUID",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_invalid_depth_negative_returns_422(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["depth"] = -1

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "depth"],
                    "msg": "Expected `int` >= 0",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_invalid_size_negative_returns_422(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["size"] = -100

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "size"],
                    "msg": "Expected `int` >= 0",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    @pytest.mark.vcr
    def test_index_title_normalization(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["title"] = "  Test Document With CAPS  "

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    def test_index_future_created_at_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        future_time = timezone.now() + timedelta(days=1)
        valid_document_payload["created_at"] = future_time.isoformat()

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body"],
                    "msg": "created_at must be earlier than now",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_future_updated_at_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        future_time = timezone.now() + timedelta(days=1)
        valid_document_payload["updated_at"] = future_time.isoformat()

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body"],
                    "msg": "updated_at must be earlier than now",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_updated_before_created_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        now = timezone.now()
        valid_document_payload["created_at"] = (now - timedelta(days=1)).isoformat()
        valid_document_payload["updated_at"] = (now - timedelta(days=2)).isoformat()

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body"],
                    "msg": "updated_at must be later than created_at",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_empty_title_and_content_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["title"] = ""
        valid_document_payload["content"] = ""

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body"],
                    "msg": "Either title or content should have at least 1 character",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    @pytest.mark.vcr
    def test_index_empty_title_with_content_accepted(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["title"] = ""
        valid_document_payload["content"] = "Valid content"

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    def test_index_invalid_group_format_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["groups"] = ["Invalid Group Name"]

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "groups0"],
                    "msg": "Expected `str` matching regex '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    @pytest.mark.vcr
    def test_index_valid_groups_accepted(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["groups"] = ["valid-group", "another-group"]

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    @pytest.mark.vcr
    def test_index_service_name_from_auth(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    @pytest.mark.vcr
    def test_index_with_reach_field(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["reach"] = "public"

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    @pytest.mark.vcr
    def test_index_with_tags(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["tags"] = ["tag1", "tag2", "important"]

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    @pytest.mark.vcr
    def test_index_with_users_and_groups(
        self,
        valid_document_payload: dict,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["users"] = ["user1", "user2"]
        valid_document_payload["groups"] = ["group-a", "group-b"]

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": valid_document_payload["id"]}

    def test_index_title_too_long_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["title"] = "x" * 301

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "title"],
                    "msg": "Expected `str` of length <= 300",
                    "type": "validation_error",
                }
            ]
        }
        mock_opensearch_client.index.assert_not_called()

    def test_index_path_too_long_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        valid_document_payload["path"] = "/" + "x" * 300

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=valid_document_payload,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        mock_opensearch_client.index.assert_not_called()

    def test_index_bulk_rejected(
        self,
        valid_document_payload: dict,
        mock_opensearch_client: MagicMock,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=[valid_document_payload, valid_document_payload],
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 422
        mock_opensearch_client.index.assert_not_called()


class TestServiceIsolation:
    @pytest.mark.vcr
    def test_service_field_from_auth_not_payload(
        self,
        mock_service_context: dict,
        bolt_client: TestClient,
    ) -> None:
        document = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "title": "Test Service Isolation",
            "content": "Test content for service isolation",
            "depth": 0,
            "path": "/test",
            "numchild": 0,
            "created_at": "2020-01-01T00:00:00+00:00",
            "updated_at": "2020-01-01T00:00:00+00:00",
            "size": 100,
            "users": [],
            "groups": [],
            "tags": [],
            "is_active": True,
            "service": "spoofed-drive",
        }

        response = bolt_client.post(
            "/api/v1.0/documents/index",
            json=document,
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 201
        assert response.json() == {"id": document["id"]}
