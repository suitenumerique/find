"""Test OpenSearch adapters"""

from core import adapters
from core.factories import IndexedDocumentSchemaFactory
from core.schemas import IndexedDocumentSchema


def test_to_opensearch():
    """Test that to_opensearch correctly converts"""
    index_document = IndexedDocumentSchema(
        **IndexedDocumentSchemaFactory(
            language_code="en",
            chunks=[
                {"text": "chunk 1", "embedding": [0.1, 0.2]},
                {"text": "chunk 2", "embedding": [0.3, 0.4]},
            ],
        )
    )

    result = adapters.to_opensearch(index_document)

    assert result["id"] == index_document.id
    assert result["depth"] == index_document.depth
    assert result["path"] == index_document.path
    assert result["numchild"] == index_document.numchild
    assert result["created_at"] == index_document.created_at
    assert result["updated_at"] == index_document.updated_at
    assert result["size"] == index_document.size
    assert result["users"] == index_document.users
    assert result["groups"] == index_document.groups
    assert result["reach"] == index_document.reach
    assert result["tags"] == index_document.tags
    assert result["is_active"] == index_document.is_active
    assert f"title.{index_document.language_code}" in result
    assert result[f"title.{index_document.language_code}"] == index_document.title
    assert f"content.{index_document.language_code}" in result
    assert result[f"content.{index_document.language_code}"] == index_document.content
    assert result["chunks"] == index_document.chunks
    assert result["embedding_model"] == index_document.embedding_model
    assert result["indexing_status"] == index_document.indexing_status
