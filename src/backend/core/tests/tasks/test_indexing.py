"""
Test suite for indexing tasks
"""

import pytest
import responses

from core.enums import IndexingStatusEnum
from core.factories import DocumentSchemaFactory
from core.models import get_opensearch_index_name
from core.services.opensearch import check_hybrid_search_enabled, opensearch_client
from core.tasks.indexing import embed_document_to_be_embedded
from core.tests.mock import albert_embedding_response
from core.tests.utils import (
    check_hybrid_search_enabled as check_hybrid_search_enabled_utils,
)
from core.tests.utils import enable_hybrid_search, prepare_index

pytestmark = pytest.mark.django_db

SERVICE_NAME = "test-tasks-service"


@pytest.fixture(autouse=True)
def before_each():
    """Clear caches before each test"""
    clear_caches()
    yield
    clear_caches()


def clear_caches():
    """Clear caches used in opensearch service and factories"""
    check_hybrid_search_enabled.cache_clear()
    check_hybrid_search_enabled_utils.cache_clear()


@responses.activate
def test_embed_document_to_be_embedded(settings):
    """Test embed_document_to_be_embedded task processes documents with TO_BE_EMBEDDED status"""
    enable_hybrid_search(settings)
    opensearch_client_ = opensearch_client()
    index_name = get_opensearch_index_name(SERVICE_NAME)

    # Create documents with TO_BE_EMBEDDED status
    documents_ready = DocumentSchemaFactory.build_batch(4)
    documents_to_be_embedded = DocumentSchemaFactory.build_batch(2)

    prepare_index(index_name, documents_to_be_embedded)
    prepare_index(index_name, documents_ready, include_embedding=True)

    # Verify documents are to-be-embedded before task execution
    opensearch_client_.indices.refresh(index=index_name)
    for i in range(2):
        hit = opensearch_client_.get(
            index=index_name,
            id=documents_to_be_embedded[i]["id"],
        )
        source = hit["_source"]
        assert source["indexing_status"] == IndexingStatusEnum.TO_BE_EMBEDDED
        assert source["embedding_model"] is None
        assert source["chunks"] is None

    responses.add(
        responses.POST,
        settings.EMBEDDING_API_PATH,
        json=albert_embedding_response.response,
        status=200,
    )

    # Execute the task
    embed_document_to_be_embedded(index_name)

    # Verify documents are READY after task execution
    opensearch_client_.indices.refresh(index=index_name)
    for i in range(2):
        hit = opensearch_client_.get(
            index=index_name,
            id=documents_to_be_embedded[i]["id"],
        )
        source = hit["_source"]
        assert source["indexing_status"] == IndexingStatusEnum.READY
        assert source["embedding_model"] == settings.EMBEDDING_API_MODEL_NAME
        assert (
            source["chunks"][0]["embedding"]
            == albert_embedding_response.response["data"][0]["embedding"]
        )
