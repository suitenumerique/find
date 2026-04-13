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
        - index_name: the name of the index to reindex with embedding
        - query: the query to select documents to reindex.
        - batch_size: the number of documents to process in each batch
        - scroll: the time to keep the search context alive for scrolling

    Returns:
        {
            "nb_failed_embedding": int,
            "nb_success_embedding": int,
        }


    returns a dict with the number of successful embeddings and failed embeddings.
    """
    opensearch_client_ = opensearch_client()
    page = opensearch_client_.search(  # pylint: disable=unexpected-keyword-arg
        index=index_name,
        scroll=scroll,
        size=batch_size,
        seq_no_primary_term=True,
        body={"query": query},
    )
    nb_failed_embedding = 0
    nb_success_embedding = 0
    while len(page["hits"]["hits"]) > 0:
        actions = []
        for hit in page["hits"]["hits"]:
            source = hit["_source"]
            chunks = chunk_document(
                get_language_value(source, "title"),
                get_language_value(source, "content"),
            )
            if chunks:
                actions.append(
                    {
                        "update": {
                            "_id": hit["_id"],
                            # if_seq_no and if_primary_term ensure we only update indexes
                            # if the document hasn't changed
                            "if_seq_no": hit["_seq_no"],
                            "if_primary_term": hit["_primary_term"],
                        }
                    }
                )
                actions.append(
                    {
                        "doc": {
                            "chunks": chunks,
                            "embedding_model": settings.EMBEDDING_API_MODEL_NAME,
                            "indexing_status": IndexingStatusEnum.READY,
                        }
                    }
                )
                nb_success_embedding += 1
            else:
                nb_failed_embedding += 1

        opensearch_client_.bulk(index=index_name, body=actions)
        page = opensearch_client_.scroll(  # pylint: disable=unexpected-keyword-arg
            scroll_id=page["_scroll_id"], scroll=scroll
        )

    opensearch_client_.clear_scroll(scroll_id=page["_scroll_id"])
    return {
        "nb_failed_embedding": nb_failed_embedding,
        "nb_success_embedding": nb_success_embedding,
    }
