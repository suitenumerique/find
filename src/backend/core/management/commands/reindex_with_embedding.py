"""
Handle reindexing of documents with embeddings in OpenSearch.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from opensearchpy.exceptions import NotFoundError

from core.services.opensearch import (
    check_hybrid_search_enabled,
    embed_text,
    format_document,
    opensearch_client,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Reindex all documents with embeddings"""

    help = __doc__
    opensearch_client_ = opensearch_client()

    def add_arguments(self, parser):
        parser.add_argument("index_name", type=str)

    def handle(self, *args, **options):
        """Launch the reindexing with embedding."""

        index_name = options["index_name"]

        if not check_hybrid_search_enabled():
            raise CommandError("Hybrid search is not enabled or properly configured.")

        try:
            self.opensearch_client_.indices.get(index=index_name)
        except NotFoundError as error:
            raise CommandError(f"Index {index_name} does not exist.") from error

        self.stdout.write(f"[INFO] Start reindexing {index_name} with embedding.")

        result = reindex_with_embedding(index_name)

        self.stdout.write(
            f"[INFO] Reindexing of {index_name} is done.\n"
            f"nb success embedding: {result['nb_success_embedding']}\n"
            f"nb failed embedding: {result['nb_failed_embedding']} embedding fails\n"
        )


def reindex_with_embedding(index_name, batch_size=500, scroll="10m"):
    """
    Reindex documents from source index to destination index with embeddings.

    returns a dict with the number of successful embeddings and failed embeddings.
    """
    opensearch_client_ = opensearch_client()
    page = opensearch_client_.search(
        index=index_name,
        scroll=scroll,
        size=batch_size,
        seq_no_primary_term=True,
        body={
            "query": {
                "bool": {
                    "should": [
                        {"bool": {"must_not": {"exists": {"field": "embedding"}}}},
                        {
                            "bool": {
                                "must_not": {
                                    "term": {
                                        "embedding_model": settings.EMBEDDING_API_MODEL_NAME
                                    }
                                }
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            }
        },
    )

    nb_failed_embedding = 0
    nb_success_embedding = 0
    while len(page["hits"]["hits"]) > 0:
        actions = []
        for hit in page["hits"]["hits"]:
            source = hit["_source"]
            embedding = embed_text(
                format_document(source.get("title", ""), source.get("content", ""))
            )
            if embedding:
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
                            "embedding": embedding,
                            "embedding_model": settings.EMBEDDING_API_MODEL_NAME,
                        }
                    }
                )
                nb_success_embedding += 1
            else:
                nb_failed_embedding += 1

        opensearch_client_.bulk(index=index_name, body=actions)
        page = opensearch_client_.scroll(scroll_id=page["_scroll_id"], scroll=scroll)

    opensearch_client_.clear_scroll(scroll_id=page["_scroll_id"])
    return {
        "nb_failed_embedding": nb_failed_embedding,
        "nb_success_embedding": nb_success_embedding,
    }
