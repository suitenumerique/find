"""Utility functions for OpenSearch testing."""

from typing import Any
from unittest.mock import MagicMock


def mock_search_response(
    hits: list[dict[str, Any]] | None = None, total: int = 0
) -> dict[str, Any]:
    """
    Create a properly structured OpenSearch search response.

    Args:
        hits: List of hit documents. Each hit should be a dict with _id and _source.
        total: Total number of matching documents.

    Returns:
        dict: Properly structured OpenSearch search response.

    Example:
        response = mock_search_response(
            hits=[{"_id": "1", "_source": {"title": "Doc"}}],
            total=1
        )
    """
    if hits is None:
        hits = []

    return {
        "hits": {
            "hits": hits,
            "total": {"value": total},
        },
        "took": 1,
        "timed_out": False,
    }


def mock_index_response(
    doc_id: str = "test-id", result: str = "created"
) -> dict[str, str]:
    """
    Create a properly structured OpenSearch index response.

    Args:
        doc_id: The document ID.
        result: The result status (e.g., "created", "updated").

    Returns:
        dict: Properly structured OpenSearch index response.

    Example:
        response = mock_index_response(doc_id="doc-123", result="created")
    """
    return {
        "_id": doc_id,
        "result": result,
    }


def mock_bulk_response(
    items: list[dict[str, Any]] | None = None, errors: bool = False
) -> dict[str, Any]:
    """
    Create a properly structured OpenSearch bulk response.

    Args:
        items: List of bulk operation results.
        errors: Whether any errors occurred.

    Returns:
        dict: Properly structured OpenSearch bulk response.

    Example:
        response = mock_bulk_response(
            items=[{"index": {"_id": "1", "result": "created"}}],
            errors=False
        )
    """
    if items is None:
        items = []

    return {
        "items": items,
        "errors": errors,
    }


def mock_delete_by_query_response(deleted: int = 0) -> dict[str, int]:
    """
    Create a properly structured OpenSearch delete_by_query response.

    Args:
        deleted: Number of documents deleted.

    Returns:
        dict: Properly structured OpenSearch delete_by_query response.

    Example:
        response = mock_delete_by_query_response(deleted=5)
    """
    return {
        "deleted": deleted,
    }


def setup_opensearch_mock(
    mock: MagicMock,
    search_hits: list[dict[str, Any]] | None = None,
    index_result: str = "created",
) -> MagicMock:
    """
    Configure a mock OpenSearch client with sensible defaults.

    Sets up return values for common OpenSearch operations:
    - search: Returns empty search response by default
    - index: Returns index response with given result
    - bulk: Returns empty bulk response
    - delete_by_query: Returns 0 deleted documents

    Args:
        mock: The MagicMock instance to configure.
        search_hits: List of hits for search response (default: []).
        index_result: Result status for index operations (default: "created").

    Returns:
        The configured mock object.

    Example:
        mock_client = MagicMock()
        setup_opensearch_mock(
            mock_client,
            search_hits=[{"_id": "1", "_source": {"title": "Doc"}}],
            index_result="created"
        )
        mock_client.search.return_value  # Returns search response with 1 hit
    """
    if search_hits is None:
        search_hits = []

    mock.search.return_value = mock_search_response(
        hits=search_hits,
        total=len(search_hits),
    )
    mock.index.return_value = mock_index_response(result=index_result)
    mock.bulk.return_value = mock_bulk_response()
    mock.delete_by_query.return_value = mock_delete_by_query_response()

    return mock
