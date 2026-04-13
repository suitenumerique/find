"""Adapters for converting between domain models and external formats."""

from .schemas import IndexedDocumentSchema


def to_opensearch(document: IndexedDocumentSchema) -> dict:
    """
    Convert indexed document to OpenSearch dictionary format.

    Args:
        document: IndexedDocumentSchema instance to convert

    Returns:
        Dictionary ready for OpenSearch indexing
    """

    return {
        "id": document.id,
        f"title.{document.language_code}": document.title,
        f"content.{document.language_code}": document.content,
        "chunks": document.chunks,
        "embedding_model": document.embedding_model,
        "indexing_status": document.indexing_status,
        "depth": document.depth,
        "path": document.path,
        "numchild": document.numchild,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "size": document.size,
        "users": document.users,
        "groups": document.groups,
        "reach": document.reach,
        "tags": document.tags,
        "is_active": document.is_active,
    }
