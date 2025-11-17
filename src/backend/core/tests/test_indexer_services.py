"""Tests indexing documents"""

from dataclasses import asdict as dataasdict
from io import StringIO
from operator import attrgetter
from unittest import mock

import pytest
import responses

from core import enums, factories
from core.services import opensearch
from core.services.indexer_services import (
    IndexBulkError,
    IndexContentError,
    IndexerTaskService,
    hit_to_doc,
    is_allowed_mimetype,
    openbulk,
)
from core.tests.utils import refresh_index

pytestmark = pytest.mark.django_db


def search_all_docs(client, index_name):
    """Helper that returns all IndexDocument available on opensearch database"""
    data = client.search(index=index_name, body={"query": {"match_all": {}}})

    return [hit_to_doc(hit) for hit in data["hits"]["hits"]]


def test_services_is_allowed_mimetype():
    """
    Check if the given mimetype matches with the allowed ones.
    """
    assert is_allowed_mimetype("", ["text/"]) is False
    assert is_allowed_mimetype("text/plain", []) is False
    assert is_allowed_mimetype("text/plain", ["text/html"]) is False
    assert is_allowed_mimetype("text/plain", ["text/"]) is True
    assert is_allowed_mimetype("application/pdf", ["text/", "application/pdf"]) is True
    assert (
        is_allowed_mimetype("application/pdf+bin", ["text/", "application/pdf"])
        is False
    )
    assert is_allowed_mimetype("application/pdf+bin", ["text/", "application/"]) is True


def test_services_openbulk():
    """Bulk opensearch actions."""
    service = factories.ServiceFactory()
    doc_create = factories.IndexDocumentFactory()
    doc_update = factories.IndexDocumentFactory()
    doc_index = factories.IndexDocumentFactory()

    opensearch_client_ = opensearch.opensearch_client()

    with pytest.raises(opensearch.NotFoundError):
        opensearch_client_.indices.get(index=service.index_name)

    with openbulk(index_name=service.index_name) as actions:
        actions.create(doc_create.id, dataasdict(doc_create))
        actions.index_document(doc_index)
        actions.index(doc_update.id, data={})
        actions.update(doc_update.id, dataasdict(doc_update))

    # now the index exists
    opensearch_client_.indices.get(index=service.index_name)

    # no errors
    assert len(actions.errors()) == 0

    # no data too... the index is not refreshed
    assert search_all_docs(opensearch_client_, service.index_name) == []

    refresh_index(service.index_name)

    # Now the docs are here
    assert sorted(
        search_all_docs(opensearch_client_, service.index_name), key=attrgetter("id")
    ) == sorted([doc_create, doc_update, doc_index], key=attrgetter("id"))


def test_services_openbulk__refresh():
    """Bulk opensearch actions and refresh the index"""
    service = factories.ServiceFactory()
    doc_create = factories.IndexDocumentFactory()
    doc_update = factories.IndexDocumentFactory()
    doc_index = factories.IndexDocumentFactory()

    opensearch_client_ = opensearch.opensearch_client()

    with pytest.raises(opensearch.NotFoundError):
        opensearch_client_.indices.get(index=service.index_name)

    with openbulk(index_name=service.index_name, refresh=True) as actions:
        actions.create(doc_create.id, dataasdict(doc_create))
        actions.index_document(doc_index)
        actions.index(doc_update.id, data={})
        actions.update(doc_update.id, dataasdict(doc_update))

    # now the index exists
    opensearch_client_.indices.get(index=service.index_name)

    # no errors
    assert len(actions.errors()) == 0

    # Auto refreshed !
    assert sorted(
        search_all_docs(opensearch_client_, service.index_name), key=attrgetter("id")
    ) == sorted([doc_create, doc_update, doc_index], key=attrgetter("id"))


def test_services_openbulk__errors():
    """Should return all bulk errors"""
    service = factories.ServiceFactory()
    doc = factories.IndexDocumentFactory()

    with openbulk(index_name=service.index_name) as actions:
        actions.create(doc.id, dataasdict(doc))
        actions.create(doc.id, dataasdict(doc))

    assert len(actions.errors()) == 1

    error = actions.errors()[0]
    assert error.id == doc.id
    assert error.action == "create"
    assert (
        error.message
        == f"[{doc.id}]: version conflict, document already exists (current version [1])"
    )


def test_services_openbulk__raise_on_status():
    """Should raise on bulk error"""
    service = factories.ServiceFactory()
    doc = factories.IndexDocumentFactory()

    with pytest.raises(IndexBulkError) as err:
        with openbulk(index_name=service.index_name, raise_on_status=True) as actions:
            actions.create(doc.id, dataasdict(doc))
            actions.create(doc.id, dataasdict(doc))

    error = err.value
    assert len(error.error_list) == 1

    error = error.error_list[0]
    assert error.id == doc.id
    assert error.action == "create"
    assert (
        error.message
        == f"[{doc.id}]: version conflict, document already exists (current version [1])"
    )


def test_services_process_content():
    """Should convert the document content with the according converter"""
    service = factories.ServiceFactory()
    indexer = IndexerTaskService(service)

    with mock.patch("core.services.indexer_services.pdf_to_markdown") as mock_pdf:
        indexer.converters = {"application/pdf": mock_pdf}

        assert (
            indexer.process_content(
                factories.IndexDocumentFactory(mimetype="text/plain"),
                StringIO("This is a test"),
            )
            == "This is a test"
        )

        mock_pdf.assert_not_called()

        assert (
            indexer.process_content(
                factories.IndexDocumentFactory(mimetype="text/plain"), "This is a test"
            )
            == "This is a test"
        )

        mock_pdf.assert_not_called()

        mock_pdf.return_value = "This a converted PDF test"
        assert (
            indexer.process_content(
                factories.IndexDocumentFactory(mimetype="application/pdf"),
                "This is a test",
            )
            == "This a converted PDF test"
        )

        mock_pdf.assert_called_once()


def test_services_process_content__error():
    """Document content process should raise an error"""
    service = factories.ServiceFactory()
    indexer = IndexerTaskService(service)

    with mock.patch("core.services.indexer_services.pdf_to_markdown") as mock_pdf:
        indexer.converters = {"application/pdf": mock_pdf}
        mock_pdf.side_effect = KeyError()

        with pytest.raises(IndexContentError):
            indexer.process_content(
                factories.IndexDocumentFactory(mimetype="application/pdf"),
                StringIO("This is a test"),
            )


def test_services_search_documents():
    """Search document as an iterable of IndexDocument"""
    service = factories.ServiceFactory()
    indexer = IndexerTaskService(service, batch_size=3)
    active_docs = factories.IndexDocumentFactory.create_batch(5)
    inactive_docs = factories.IndexDocumentFactory.create_batch(3, is_active=False)
    docs = active_docs + inactive_docs

    assert not list(indexer.search_documents({"match_all": {}}))

    indexer.index(docs)

    assert list(indexer.search_documents({"match_all": {}})) == sorted(
        docs, key=attrgetter("id")
    )
    assert list(
        indexer.search_documents({"bool": {"must": {"term": {"is_active": True}}}})
    ) == sorted(active_docs, key=attrgetter("id"))
    assert list(
        indexer.search_documents({"bool": {"must": {"term": {"is_active": False}}}})
    ) == sorted(inactive_docs, key=attrgetter("id"))


def test_services_search_documents__as_batch():
    """Search document as an iterable of list of IndexDocument (batches)"""
    service = factories.ServiceFactory()
    indexer = IndexerTaskService(service, batch_size=3)
    docs = [
        factories.IndexDocumentFactory(
            id=f"00000000-0000-0000-0000-0000000000{index:02d}"  # fake uuid to know order
        )
        for index in range(1, 10)
    ]

    assert not list(indexer.search_documents({"match_all": {}}, as_batch=True))

    indexer.index(docs)

    assert list(indexer.search_documents({"match_all": {}}, as_batch=True)) == [
        docs[:3],
        docs[3:6],
        docs[6:],
    ]


@pytest.mark.parametrize(
    "content_uri, content, mimetype, processed, status",
    (
        ("", "", "text/plain", False, enums.ContentStatusEnum.READY),
        ("", "", "application/pdf", True, enums.ContentStatusEnum.READY),
        (
            "http://localhost/mydoc",
            "",
            "application/pdf",
            False,
            enums.ContentStatusEnum.WAIT,
        ),
        (
            "http://localhost/mydoc",
            "This is a test",
            "application/pdf",
            True,
            enums.ContentStatusEnum.READY,
        ),
        ("", "This is a test", "application/pdf", True, enums.ContentStatusEnum.READY),
        ("", "This is a test", "text/plain", False, enums.ContentStatusEnum.READY),
    ),
)
def test_service_index(content_uri, content, mimetype, processed, status):
    """Add documents to index and set the content_status depending of their properties"""
    service = factories.ServiceFactory()
    indexer = IndexerTaskService(service)
    doc = factories.IndexDocumentFactory(
        mimetype=mimetype, content_uri=content_uri, content=content
    )

    with mock.patch("core.services.indexer_services.pdf_to_markdown") as mock_pdf:
        mock_pdf.return_value = "processed content"
        indexer.converters = {"application/pdf": mock_pdf}
        errors = indexer.index([doc])

    assert len(errors) == 0
    assert mock_pdf.called == processed

    indexed_docs = list(indexer.search_documents({"match_all": {}}))
    assert len(indexed_docs) == 1

    indexed_doc = indexed_docs[0]
    assert indexed_doc.content_status == status


@pytest.mark.parametrize(
    "status, mimetype, is_active , expected",
    (
        (
            enums.ContentStatusEnum.READY,
            "plain/text",
            True,
            {
                "content": "initial content",
                "status": enums.ContentStatusEnum.READY,
            },
        ),
        (
            enums.ContentStatusEnum.LOADED,
            "plain/text",
            True,
            {
                "content": "initial content",
                "status": enums.ContentStatusEnum.LOADED,
            },
        ),
        (
            enums.ContentStatusEnum.WAIT,
            "plain/text",
            True,
            {
                "content": "loaded content",
                "status": enums.ContentStatusEnum.READY,
            },
        ),
        (
            enums.ContentStatusEnum.WAIT,
            "application/pdf",
            True,
            {
                "content": "processed content",
                "status": enums.ContentStatusEnum.READY,
            },
        ),
        (
            enums.ContentStatusEnum.WAIT,
            "plain/text",
            False,
            {
                "content": "initial content",
                "status": enums.ContentStatusEnum.WAIT,
            },
        ),
    ),
)
@responses.activate
def test_service_load_all(status, mimetype, is_active, expected):
    """Documents content should be downloaded and processed if needed"""
    service = factories.ServiceFactory()
    indexer = IndexerTaskService(service)
    docs = factories.IndexDocumentFactory.create_batch(
        3,
        mimetype=mimetype,
        content_status=status,
        content_uri="http://localhost/mydoc",
        content="initial content",
        is_active=is_active,
    )

    with openbulk(service.index_name, refresh=True) as actions:
        for doc in docs:
            actions.index_document(doc)

    responses.add(
        responses.GET,
        "http://localhost/mydoc",
        body="loaded content",
        status=200,
    )

    indexed_docs = list(indexer.search_documents({"match_all": {}}))
    assert [d.content_status for d in indexed_docs] == [status] * 3
    assert [d.is_active for d in indexed_docs] == [is_active] * 3

    with mock.patch("core.services.indexer_services.pdf_to_markdown") as mock_pdf:
        mock_pdf.return_value = "processed content"
        indexer.converters = {"application/pdf": mock_pdf}
        errors = indexer.load_all()

    assert len(errors) == 0

    indexed_docs = list(indexer.search_documents({"match_all": {}}))
    assert [d.content_status for d in indexed_docs] == [expected["status"]] * 3
    assert [d.content for d in indexed_docs] == [expected["content"]] * 3
