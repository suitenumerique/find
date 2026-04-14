"""Utility functions for Test."""

import base64
import json
import logging
from functools import partial
from typing import List

from django.conf import settings as django_settings

from opensearchpy.helpers import bulk

from core import adapters
from core.enums import IndexingStatusEnum
from core.management.commands.create_search_pipeline import (
    ensure_search_pipeline_exists,
)
from core.schemas import IndexedDocumentSchema
from core.services.indexing import detect_language_code, ensure_index_exists
from core.services.opensearch import (
    check_hybrid_search_enabled,
    opensearch_client,
)
from core.tests.mock import albert_embedding_response

logger = logging.getLogger(__name__)


def enable_hybrid_search(settings):
    """Enable hybrid search settings for tests."""
    settings.HYBRID_SEARCH_ENABLED = True
    settings.HYBRID_SEARCH_WEIGHTS = [0.3, 0.7]
    settings.EMBEDDING_API_KEY = "test-api-key"
    settings.EMBEDDING_API_PATH = "https://test.embedding.api/v1/embeddings"
    settings.EMBEDDING_REQUEST_TIMEOUT = 10
    settings.EMBEDDING_API_MODEL_NAME = "embeddings-small"
    settings.EMBEDDING_DIMENSION = 1024

    # Clear the cache here or the hybrid search will remain disabled
    check_hybrid_search_enabled.cache_clear()
    ensure_search_pipeline_exists()


def build_authorization_bearer(token="some_token"):
    """
    Build an Authorization Bearer header value from a token.

    This can be used like this:
    client.post(
        ...
        HTTP_AUTHORIZATION=f"Bearer {build_authorization_bearer('some_token')}",
    )
    """
    return base64.b64encode(token.encode("utf-8")).decode("utf-8")


def setup_oicd_resource_server(
    responses,
    settings,
    sub="some_sub",
    audience="some_client_id",
    introspect=None,
):  # pylint: disable=too-many-arguments
    """
    Setup settings for a resource server.
    Simulate a token introspection.
    NOTE : Use it with @responses.activate or the fake introspection view will not work.
    """
    token_data = {
        "sub": sub,
        "iss": "https://oidc.example.com",
        "aud": audience,
        "client_id": audience,
        "scope": "docs",
        "active": True,
    }

    settings.OIDC_RS_ENCRYPTION_KEY_TYPE = "RSA"
    settings.OIDC_RS_ENCRYPTION_ENCODING = "A256GCM"
    settings.OIDC_RS_ENCRYPTION_ALGO = "RSA-OAEP"
    settings.OIDC_RS_SIGNING_ALGO = "RS256"
    settings.OIDC_RS_CLIENT_ID = audience
    settings.OIDC_RS_CLIENT_SECRET = "some_client_secret"
    settings.OIDC_RS_SCOPES = ["openid", "docs", "email"]

    settings.OIDC_OP_URL = "https://oidc.example.com"
    settings.OIDC_OP_INTROSPECTION_ENDPOINT = "https://oidc.example.com/introspect"

    settings.OIDC_VERIFY_SSL = False
    settings.OIDC_TIMEOUT = 5
    settings.OIDC_PROXY = None
    settings.OIDC_CREATE_USER = False

    if callable(introspect):
        responses.add_callback(
            responses.POST,
            settings.OIDC_OP_INTROSPECTION_ENDPOINT,
            callback=partial(introspect, user_info=token_data),
        )
    else:
        responses.add(
            responses.POST,
            settings.OIDC_OP_INTROSPECTION_ENDPOINT,
            body=json.dumps(token_data),
        )


def prepare_index(index_name, documents: List, include_embedding=False):
    """Prepare the search index before testing a query on it."""
    logger.info("Preparing index %s with %d documents", index_name, len(documents))

    ensure_index_exists(index_name)
    actions = [
        {
            "_op_type": "index",
            "_index": index_name,
            "_id": document["id"],
            "_source": prepare_document_for_indexing(document, include_embedding),
        }
        for document in documents
    ]
    bulk(opensearch_client(), actions)
    opensearch_client().indices.refresh(index=index_name)


def prepare_document_for_indexing(document: dict, include_embedding: bool) -> dict:
    """
    Mocks the indexing of a document.
    Can mock the indexing after the chunking and embedding task with include_embedding.
    """
    language_code = detect_language_code(f"{document['title']} {document['content']}")
    chunks = mocked_chunk_document(document["content"]) if include_embedding else None
    embedding_model = django_settings.EMBEDDING_API_MODEL_NAME if chunks else None
    indexing_status = (
        IndexingStatusEnum.READY
        if chunks or not check_hybrid_search_enabled()
        else IndexingStatusEnum.TO_BE_EMBEDDED
    )

    indexed_document = IndexedDocumentSchema(
        id=document["id"],
        title=document["title"],
        content=document["content"],
        language_code=language_code,
        chunks=chunks,
        embedding_model=embedding_model,
        indexing_status=indexing_status,
        depth=document["depth"],
        path=document["path"],
        numchild=document["numchild"],
        created_at=document["created_at"],
        updated_at=document["updated_at"],
        size=document["size"],
        users=document["users"],
        groups=document["groups"],
        reach=document["reach"],
        tags=document.get("tags", []),
        is_active=document["is_active"],
    )

    return adapters.to_opensearch(indexed_document)


def mocked_chunk_document(document_content):
    """Mocked chunk document function for testing."""
    return [
        {
            "index": 0,
            "content": document_content[: len(document_content) // 2],
            "embedding": albert_embedding_response.response["data"][0]["embedding"],
        },
        {
            "index": 1,
            "content": document_content[len(document_content) // 2 :],
            "embedding": albert_embedding_response.response["data"][0]["embedding"],
        },
    ]
