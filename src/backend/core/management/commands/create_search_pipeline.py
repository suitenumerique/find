"""
Handle create the search pipeline command of the hybrid search.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from opensearchpy.exceptions import NotFoundError

from core.services.opensearch import (
    opensearch_client,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Handle create the search pipeline command of the hybrid search."""

    help = __doc__

    def handle(self, *args, **options):
        ensure_search_pipeline_exists()


def ensure_search_pipeline_exists():
    """Create search pipeline for hybrid search if it does not exist"""
    try:
        opensearch_client().search_pipeline.get(settings.HYBRID_SEARCH_PIPELINE_ID)
        logger.info("Search pipeline exists already")
    except NotFoundError:
        logger.info("Creating search pipeline: %s", settings.HYBRID_SEARCH_PIPELINE_ID)
        opensearch_client().transport.perform_request(
            method="PUT",
            url="/_search/pipeline/" + settings.HYBRID_SEARCH_PIPELINE_ID,
            body={
                "description": "Post processor for hybrid search",
                "phase_results_processors": [
                    {
                        "normalization-processor": {
                            "combination": {
                                "technique": "arithmetic_mean",
                                "parameters": {
                                    "weights": settings.HYBRID_SEARCH_WEIGHTS
                                },
                            }
                        }
                    }
                ],
            },
        )
