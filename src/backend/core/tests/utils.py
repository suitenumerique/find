"""Tests Service model for find's core app."""

from opensearchpy.helpers import bulk

from core import opensearch


def prepare_index(index_name, documents):
    """Prepare the search index before testing a query on it."""
    opensearch.client.indices.delete(index="*test*")
    opensearch.ensure_index_exists(index_name)

    # Index new documents
    documents = documents if isinstance(documents, list) else [documents]
    actions = [
        {
            "_op_type": "index",
            "_index": index_name,
            "_id": doc["id"],
            "_source": {k: v for k, v in doc.items() if k != "id"},
        }
        for doc in documents
    ]
    bulk(opensearch.client, actions)

    # Force refresh again so all changes are visible to search
    opensearch.client.indices.refresh(index=index_name)

    count = opensearch.client.count(index=index_name)["count"]
    assert count == len(documents), f"Expected {len(documents)}, got {count}"
