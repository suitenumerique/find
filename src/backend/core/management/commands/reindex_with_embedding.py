"""
Handle reindexing of documents with embeddings in OpenSearch.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import requests
from opensearchpy.exceptions import NotFoundError

from core.services.opensearch import (
    check_hybrid_search_enabled,
    embed_text,
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
        self.opensearch_client_.indices.refresh(index=index_name)

        self.stdout.write(
            f"[INFO] Reindexing of {index_name} was done "
            f"with {result['nb_failed_embedding']} embedding fails."
        )


def reindex_with_embedding(index_name, batch_size=500):
    """Reindex documents from source index to destination index with embeddings."""
    opensearch_client_ = opensearch_client()
    page = opensearch_client_.search(
        index=index_name,
        scroll="10m",
        size=batch_size,
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

    while len(page["hits"]["hits"]) > 0:
        actions = []
        for hit in page["hits"]["hits"]:
            document = hit["_source"]
            try:
                actions.append({"update": {"_id": hit["_id"]}})
                actions.append(
                    {
                        "doc": {
                            "embedding": embed_text(
                                f"<{document.get('text')}>:<{document.get('content')}>"
                            ),
                            "embedding_model": settings.EMBEDDING_API_MODEL_NAME,
                        }
                    }
                )
            except requests.HTTPError as error:
                logger.warning("embedding failed: %d", error)
                nb_failed_embedding += 1

        opensearch_client_.bulk(index=index_name, body=actions)
        page = opensearch_client_.scroll(scroll_id=page["_scroll_id"], scroll="5m")

    opensearch_client_.clear_scroll(scroll_id=page["_scroll_id"])
    return {"nb_failed_embedding": nb_failed_embedding}
