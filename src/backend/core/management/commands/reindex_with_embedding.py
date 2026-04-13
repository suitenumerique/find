"""
Handle reindexing documents without embedding or embedded with deprecated embedding model.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from opensearchpy.exceptions import NotFoundError

from core.models import get_opensearch_index_name
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client
from core.services.reindex import reindex_with_embedding

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Reindex all documents with embeddings"""

    help = __doc__
    opensearch_client_ = opensearch_client()

    def add_arguments(self, parser):
        parser.add_argument("index_name", type=str)

    def handle(self, *args, **options):
        """Launch the reindexing with embedding."""

        index_name = get_opensearch_index_name(options["index_name"])

        if not check_hybrid_search_enabled():
            raise CommandError("Hybrid search is not enabled or properly configured.")

        try:
            self.opensearch_client_.indices.get(index=index_name)
        except NotFoundError as error:
            raise CommandError(f"Index {index_name} does not exist.") from error

        self.stdout.write(f"[INFO] Start reindexing {index_name} with embedding.")

        result = reindex_with_embedding(
            index_name,
            {
                "bool": {
                    "should": [
                        {
                            "bool": {
                                "must_not": [
                                    {
                                        "nested": {
                                            "path": "chunks",
                                            "query": {"match_all": {}},
                                        }
                                    }
                                ]
                            }
                        },
                        {
                            "bool": {
                                "must_not": [
                                    {
                                        "term": {
                                            "embedding_model": settings.EMBEDDING_API_MODEL_NAME
                                        }
                                    }
                                ]
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            },
        )

        self.stdout.write(
            f"[INFO] Reindexing of {index_name} is done.\n"
            f"nb success embedding: {result['nb_success_embedding']}\n"
            f"nb failed embedding: {result['nb_failed_embedding']} embedding fails\n"
        )
