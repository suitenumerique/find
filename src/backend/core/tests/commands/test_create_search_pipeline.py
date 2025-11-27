"""
Unit test for `create_search_pipeline` command.
"""

import logging

from django.core.management import call_command

import pytest

from core.services.opensearch import opensearch_client
from core.tests.utils import (
    delete_search_pipeline,
    enable_hybrid_search,
)


@pytest.fixture(autouse=True)
def before_each():
    """Delete search pipeline before each test"""
    delete_search_pipeline()
    yield
    delete_search_pipeline()


def test_create_search_pipeline(settings, caplog):
    """Test command create search pipeline"""

    enable_hybrid_search(settings)

    with caplog.at_level(logging.INFO):
        call_command("create_search_pipeline")

    assert any(
        f"Creating search pipeline: {settings.HYBRID_SEARCH_PIPELINE_ID}" in message
        for message in caplog.messages
    )

    # calling get works without raising NotFoundError
    opensearch_client().search_pipeline.get(id=settings.HYBRID_SEARCH_PIPELINE_ID)


def test_create_search_pipeline_but_it_exists_already(settings, caplog):
    """Test command create search pipeline but it already exists"""

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
                            "parameters": {"weights": settings.HYBRID_SEARCH_WEIGHTS},
                        }
                    }
                }
            ],
        },
    )

    with caplog.at_level(logging.INFO):
        call_command("create_search_pipeline")

    assert any(
        "Search pipeline exists already" in message for message in caplog.messages
    )
    assert not any(
        f"Creating search pipeline: {settings.HYBRID_SEARCH_PIPELINE_ID}" in message
        for message in caplog.messages
    )

    # the pipeline is still here
    opensearch_client().search_pipeline.get(id=settings.HYBRID_SEARCH_PIPELINE_ID)
