"""Integration tests for the per-service OpenSearch index architecture.

These tests exercise the full cross-cutting behaviour of the index-splitting
architecture: fan-out search, cross-service delete, service activation gating,
per-user access isolation, and Service.name immutability.

Service instances use auto-generated names (via ServiceFactory sequence) to
avoid unique-constraint collisions when the suite runs under pytest-xdist.
Index names are derived from the actual service.name at runtime.
"""

from django.core.exceptions import ValidationError

import pytest
import responses as responses_lib
from rest_framework.test import APIClient

from core import enums, factories
from core.services.indexing import (
    ensure_index_exists,
    get_all_active_service_indices,
    get_service_index_name,
)
from core.services.opensearch import opensearch_client
from core.services.search import search

from .utils import build_authorization_bearer, setup_oicd_resource_server

pytestmark = pytest.mark.django_db


def _index_via_api(service, documents):
    """Index a list of documents through the service bearer-token API endpoint.

    Args:
        service: A Service instance whose token authorises the request.
        documents: A list of document dicts produced by DocumentFactory.build().
    """
    if not isinstance(documents, list):
        documents = [documents]
    response = APIClient().post(
        "/api/v1.0/documents/index/",
        documents,
        HTTP_AUTHORIZATION=f"Bearer {service.token:s}",
        format="json",
    )
    assert response.status_code == 201


def _refresh_index(index_name):
    """Force an OpenSearch index refresh so newly indexed docs are searchable immediately.

    Args:
        index_name: The fully-qualified OpenSearch index name to refresh.
    """
    opensearch_client().indices.refresh(index=index_name)


@responses_lib.activate
def test_full_roundtrip_two_services(settings):
    """Full roundtrip across two services: index, search, delete, confirm gone.

    - Index doc A via one service and doc B via another service.
    - Fan-out search returns both docs.
    - Fan-out delete removes both docs.
    - Follow-up search returns empty.
    """
    user_sub = "roundtrip-user-sub"
    setup_oicd_resource_server(responses_lib, settings, sub=user_sub)

    svc_a = factories.ServiceFactory()
    svc_b = factories.ServiceFactory()

    doc_a = factories.DocumentFactory.build(users=[user_sub])
    doc_b = factories.DocumentFactory.build(users=[user_sub])

    _index_via_api(svc_a, [doc_a])
    _index_via_api(svc_b, [doc_b])

    idx_a = f"{settings.OPENSEARCH_INDEX_PREFIX}-{svc_a.name}"
    idx_b = f"{settings.OPENSEARCH_INDEX_PREFIX}-{svc_b.name}"
    _refresh_index(idx_a)
    _refresh_index(idx_b)

    # Fan-out search — both docs must appear
    search_resp = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )
    assert search_resp.status_code == 200
    result_ids = [hit["_id"] for hit in search_resp.json()]
    assert doc_a["id"] in result_ids
    assert doc_b["id"] in result_ids

    # Fan-out delete — both docs must be removed
    delete_resp = APIClient().post(
        "/api/v1.0/documents/delete/",
        {"document_ids": [doc_a["id"], doc_b["id"]]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["nb-deleted-documents"] == 2

    _refresh_index(idx_a)
    _refresh_index(idx_b)

    # Follow-up search — both docs must be gone
    search_resp2 = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )
    assert search_resp2.status_code == 200
    result_ids2 = [hit["_id"] for hit in search_resp2.json()]
    assert doc_a["id"] not in result_ids2
    assert doc_b["id"] not in result_ids2


@responses_lib.activate
def test_deactivated_service_hidden_then_reactivated_visible(settings):
    """Deactivating a service excludes it from search fan-out; reactivating restores it.

    - Index docX via a service — search finds docX.
    - Set Service.is_active = False — search does NOT find docX (excluded from fan-out).
    - Set Service.is_active = True — search finds docX again.
    """
    user_sub = "archive-user-sub"
    setup_oicd_resource_server(responses_lib, settings, sub=user_sub)

    svc = factories.ServiceFactory()
    doc_x = factories.DocumentFactory.build(users=[user_sub])

    _index_via_api(svc, [doc_x])
    svc_idx = f"{settings.OPENSEARCH_INDEX_PREFIX}-{svc.name}"
    _refresh_index(svc_idx)

    # Service active — docX must be visible
    resp_active = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )
    assert resp_active.status_code == 200
    assert doc_x["id"] in [hit["_id"] for hit in resp_active.json()]

    # Deactivate service — fan-out must skip this service's index
    svc.is_active = False
    svc.save()

    resp_inactive = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )
    assert resp_inactive.status_code == 200
    assert doc_x["id"] not in [hit["_id"] for hit in resp_inactive.json()]

    # Reactivate service — docX must be visible again
    svc.is_active = True
    svc.save()

    resp_reactivated = APIClient().post(
        "/api/v1.0/documents/search/",
        {"q": "*"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer()}",
    )
    assert resp_reactivated.status_code == 200
    assert doc_x["id"] in [hit["_id"] for hit in resp_reactivated.json()]


def test_user_only_sees_own_docs_across_indices(settings):
    """Cross-service user isolation: each user only sees documents they can access.

    - docA indexed in one service with restricted reach, only u1 in users.
    - docB indexed in another service with restricted reach, only u2 in users.
    - Searching as u1 returns docA and NOT docB.
    - Searching as u2 returns docB and NOT docA.
    """
    u1_sub = "isolation-user-one"
    u2_sub = "isolation-user-two"

    svc_a = factories.ServiceFactory()
    svc_b = factories.ServiceFactory()

    doc_a = factories.DocumentFactory.build(
        users=[u1_sub], reach=enums.ReachEnum.RESTRICTED.value
    )
    doc_b = factories.DocumentFactory.build(
        users=[u2_sub], reach=enums.ReachEnum.RESTRICTED.value
    )

    _index_via_api(svc_a, [doc_a])
    _index_via_api(svc_b, [doc_b])

    _refresh_index(f"{settings.OPENSEARCH_INDEX_PREFIX}-{svc_a.name}")
    _refresh_index(f"{settings.OPENSEARCH_INDEX_PREFIX}-{svc_b.name}")

    indices = get_all_active_service_indices()

    # u1 must see docA only
    result_u1 = search(
        q="*",
        nb_results=50,
        order_by=enums.RELEVANCE,
        order_direction="desc",
        search_indices=indices,
        reach=None,
        visited=[],
        user_sub=u1_sub,
        groups=[],
        tags=[],
    )
    u1_ids = [hit["_id"] for hit in result_u1["hits"]["hits"]]
    assert doc_a["id"] in u1_ids
    assert doc_b["id"] not in u1_ids

    # u2 must see docB only
    result_u2 = search(
        q="*",
        nb_results=50,
        order_by=enums.RELEVANCE,
        order_direction="desc",
        search_indices=indices,
        reach=None,
        visited=[],
        user_sub=u2_sub,
        groups=[],
        tags=[],
    )
    u2_ids = [hit["_id"] for hit in result_u2["hits"]["hits"]]
    assert doc_b["id"] in u2_ids
    assert doc_a["id"] not in u2_ids


def test_service_name_immutable_blocks_rename(settings):
    """Service.name is immutable: a rename attempt raises ValidationError.

    The original OpenSearch index is unaffected — its name is derived from the
    immutable service name, so the rename attempt cannot silently corrupt the
    index topology.

    - Create a service and its OpenSearch index.
    - Attempt to rename the service → ValidationError is raised.
    - The original index still exists under its original name.
    - No index under the attempted new name was created.
    """
    svc = factories.ServiceFactory()
    original_index = get_service_index_name(svc.name)
    ensure_index_exists(original_index)

    client = opensearch_client()
    assert client.indices.exists(index=original_index)

    # Attempt rename — must raise ValidationError
    svc.name = "immutable-rename-tgt"
    with pytest.raises(ValidationError):
        svc.save()

    # Original index must still exist unchanged
    assert client.indices.exists(index=original_index)

    # No index must have been created for the attempted new name
    renamed_idx = f"{settings.OPENSEARCH_INDEX_PREFIX}-immutable-rename-tgt"
    assert not client.indices.exists(index=renamed_idx)
