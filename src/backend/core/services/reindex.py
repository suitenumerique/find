"""Service to reindex documents with embedding."""

from django.conf import settings

from core.enums import IndexingStatusEnum
from core.services.indexing import chunk_document
from core.services.opensearch import opensearch_client
from core.utils import get_language_value


def reindex_with_embedding(index_name, query, batch_size=500, scroll="10m"):
    """
    Reindex documents from source index to destination index with embeddings.

    Args:
        index_name: The name of the index to reindex with embedding
        query: The query to select documents to reindex
        batch_size: The number of documents to process in each batch
        scroll: The time to keep the search context alive for scrolling

    Returns:
        dict: {
            "nb_failed_embedding": int,
            "nb_success_embedding": int,
        }
    """
    opensearch_client_ = opensearch_client()
    nb_failed_embedding = 0
    nb_success_embedding = 0

    for batch in offset_page(index_name, query, batch_size, scroll):
        batch_actions = []
        for hit in batch:
            success, actions = process_document_for_embedding(hit)

            if success:
                batch_actions.extend(actions)
                nb_success_embedding += 1
            else:
                nb_failed_embedding += 1

        if batch_actions:
            opensearch_client_.bulk(index=index_name, body=batch_actions)

    return {
        "nb_failed_embedding": nb_failed_embedding,
        "nb_success_embedding": nb_success_embedding,
    }


def process_document_for_embedding(hit):
    """Process a single document to add embeddings."""
    source = hit["_source"]
    chunks = chunk_document(
        get_language_value(source, "title"),
        get_language_value(source, "content"),
    )

    if not chunks:
        return False, None

    actions = [
        {
            "update": {
                "_id": hit["_id"],
                # if_seq_no and if_primary_term ensure we only update
                # if the document hasn't changed
                "if_seq_no": hit["_seq_no"],
                "if_primary_term": hit["_primary_term"],
            }
        },
        {
            "doc": {
                "chunks": chunks,
                "embedding_model": settings.EMBEDDING_API_MODEL_NAME,
                "indexing_status": IndexingStatusEnum.READY,
            }
        },
    ]
    return True, actions


def offset_page(index_name, query, batch_size=500, scroll="10m"):
    """Generator to batch yields documents from OpenSearch."""
    opensearch_client_ = opensearch_client()
    page = opensearch_client_.search(  # pylint: disable=unexpected-keyword-arg
        index=index_name,
        scroll=scroll,
        size=batch_size,
        seq_no_primary_term=True,
        body={"query": query},
    )

    while len(page["hits"]["hits"]) > 0:
        yield page["hits"]["hits"]
        page = opensearch_client_.scroll(  # pylint: disable=unexpected-keyword-arg
            scroll_id=page["_scroll_id"], scroll=scroll
        )

    opensearch_client_.clear_scroll(scroll_id=page["_scroll_id"])
