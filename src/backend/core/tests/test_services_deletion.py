"""
Test suite for the opensearch deletion service
"""

from unittest import mock

import pytest

from core import factories
from core.services.deletion import delete_documents
from core.services.opensearch import opensearch_client, run_async
from core.utils import prepare_index

pytestmark = pytest.mark.django_db


def get_indexed_ids(index_name):
    """Return the ids of the documents of an index"""
    opensearch_client().indices.refresh(index=index_name)
    response = opensearch_client().search(
        index=index_name, body={"query": {"match_all": {}}}
    )
    return {hit["_id"] for hit in response["hits"]["hits"]}


def test_services_deletion_owned_documents_only():
    """Only the requested documents listing the user should be deleted."""
    service = factories.ServiceFactory()
    owned = factories.DocumentSchemaFactory.build_batch(3, users=["user_sub"])
    not_owned = factories.DocumentSchemaFactory.build(users=["other_sub"])
    prepare_index(service.index_name, [*owned, not_owned])

    result = run_async(
        delete_documents,
        service.index_name,
        "user_sub",
        document_ids=[owned[0]["id"], owned[1]["id"], not_owned["id"], "unknown"],
    )

    assert result == (2, [not_owned["id"], "unknown"])
    assert get_indexed_ids(service.index_name) == {owned[2]["id"], not_owned["id"]}


def test_services_deletion_document_ids_and_tags():
    """Document ids and tags should be combined with AND."""
    service = factories.ServiceFactory()
    tagged = factories.DocumentSchemaFactory.build_batch(
        2, users=["user_sub"], tags=["tag"]
    )
    untagged = factories.DocumentSchemaFactory.build(users=["user_sub"])
    prepare_index(service.index_name, [*tagged, untagged])

    result = run_async(
        delete_documents,
        service.index_name,
        "user_sub",
        document_ids=[tagged[0]["id"], untagged["id"]],
        tags=["tag"],
    )

    assert result == (1, [untagged["id"]])
    assert get_indexed_ids(service.index_name) == {tagged[1]["id"], untagged["id"]}


def test_services_deletion_tags_only():
    """All the user's documents with one of the tags should be deleted."""
    service = factories.ServiceFactory()
    tagged = factories.DocumentSchemaFactory.build(users=["user_sub"], tags=["a"])
    other_tagged = factories.DocumentSchemaFactory.build(users=["user_sub"], tags=["b"])
    untagged = factories.DocumentSchemaFactory.build(users=["user_sub"])
    prepare_index(service.index_name, [tagged, other_tagged, untagged])

    result = run_async(
        delete_documents, service.index_name, "user_sub", tags=["a", "b"]
    )

    assert result == (2, [])
    assert get_indexed_ids(service.index_name) == {untagged["id"]}


def test_services_deletion_other_index_untouched():
    """Only the given index should be affected."""
    service = factories.ServiceFactory()
    other_service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build(users=["user_sub"])
    prepare_index(service.index_name, [document])
    prepare_index(other_service.index_name, [document])

    nb_deleted, _ = run_async(
        delete_documents,
        service.index_name,
        "user_sub",
        document_ids=[document["id"]],
    )

    assert nb_deleted == 1
    assert get_indexed_ids(service.index_name) == set()
    assert get_indexed_ids(other_service.index_name) == {document["id"]}


def test_services_deletion_nothing_to_delete():
    """No delete request should be sent when no document matches."""
    service = factories.ServiceFactory()
    document = factories.DocumentSchemaFactory.build(users=["other_sub"])
    prepare_index(service.index_name, [document])

    with mock.patch(
        "opensearchpy.AsyncOpenSearch.delete_by_query", new_callable=mock.AsyncMock
    ) as delete_by_query:
        result = run_async(
            delete_documents,
            service.index_name,
            "user_sub",
            document_ids=[document["id"]],
        )

    assert result == (0, [document["id"]])
    delete_by_query.assert_not_called()
    assert get_indexed_ids(service.index_name) == {document["id"]}


def test_services_deletion_more_than_ten_documents_by_tags():
    """All the documents matching the tags should be deleted, not only the first 10."""
    service = factories.ServiceFactory()
    tagged = factories.DocumentSchemaFactory.build_batch(
        15, users=["user_sub"], tags=["tag"]
    )
    not_owned = factories.DocumentSchemaFactory.build(users=["other"], tags=["tag"])
    prepare_index(service.index_name, [*tagged, not_owned])

    with mock.patch(
        "opensearchpy.AsyncOpenSearch.search", new_callable=mock.AsyncMock
    ) as search:
        result = run_async(
            delete_documents, service.index_name, "user_sub", tags=["tag"]
        )

    assert result == (15, [])
    # The ids of the deleted documents are only needed when ids are requested
    search.assert_not_called()
    assert get_indexed_ids(service.index_name) == {not_owned["id"]}


def test_services_deletion_more_than_ten_documents_by_ids():
    """All the requested documents should be deleted, not only the first 10."""
    service = factories.ServiceFactory()
    owned = factories.DocumentSchemaFactory.build_batch(15, users=["user_sub"])
    not_owned = factories.DocumentSchemaFactory.build_batch(3, users=["other"])
    prepare_index(service.index_name, [*owned, *not_owned])

    requested_ids = [document["id"] for document in [*not_owned, *owned]]
    result = run_async(
        delete_documents, service.index_name, "user_sub", document_ids=requested_ids
    )

    assert result == (15, requested_ids[:3])
    assert get_indexed_ids(service.index_name) == {d["id"] for d in not_owned}
