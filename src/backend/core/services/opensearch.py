"""Opensearch related utils."""

import logging
from functools import cache
from typing import List, Dict, Any

from django.conf import settings

from langchain_text_splitters import RecursiveCharacterTextSplitter
import requests
from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from py3langid.langid import MODEL_FILE, LanguageIdentifier
from rest_framework.exceptions import ValidationError

from core import enums
from core.services.opensearch_configuration import (
    ANALYZERS,
    FILTERS,
    MAPPINGS,
)

logger = logging.getLogger(__name__)


REQUIRED_ENV_VARIABLES = [
    "OPENSEARCH_HOST",
    "OPENSEARCH_PORT",
    "OPENSEARCH_USER",
    "OPENSEARCH_PASSWORD",
    "OPENSEARCH_USE_SSL",
]
# see https://pypi.org/project/py3langid/
LANGUAGE_IDENTIFIER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
LANGUAGE_IDENTIFIER.set_languages(["en", "fr", "de", "nl"])


TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP,
)

@cache
def opensearch_client():
    """Get OpenSearch client, ensuring required env variables are set"""
    missing_env_variables = [
        variable
        for variable in REQUIRED_ENV_VARIABLES
        if getattr(settings, variable, None) is None
    ]
    if missing_env_variables:
        raise ValidationError(
            f"Missing required OpenSearch environment variables: {', '.join(missing_env_variables)}"
        )

    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        timeout=50,
        use_ssl=settings.OPENSEARCH_USE_SSL,
        verify_certs=False,
    )


# pylint: disable=too-many-arguments, too-many-positional-arguments
def search(  # noqa : PLR0913
    q,
    nb_results,
    order_by,
    order_direction,
    search_indices,
    reach,
    visited,
    user_sub,
    groups,
):
    """Perform an OpenSearch search"""
    query = get_query(
        q=q,
        nb_results=nb_results,
        reach=reach,
        visited=visited,
        user_sub=user_sub,
        groups=groups,
    )
    return opensearch_client().search(  # pylint: disable=unexpected-keyword-arg
        index=",".join(search_indices),
        body={
            "_source": enums.SOURCE_FIELDS,  # limit the fields to return
            "script_fields": {
                "number_of_users": {"script": {"source": "doc['users'].size()"}},
                "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
            },
            "sort": get_sort(
                query_keys=query.keys(),
                order_by=order_by,
                order_direction=order_direction,
            ),
            "size": nb_results,
            # Compute query
            "query": query,
        },
        params=get_params(query_keys=query.keys()),
        # disable=unexpected-keyword-arg because
        # ignore_unavailable is not in the the method declaration
        ignore_unavailable=True,
    )


# pylint: disable=too-many-arguments, too-many-positional-arguments
def get_query(  # noqa : PLR0913
    q, nb_results, reach, visited, user_sub, groups
):
    """Build OpenSearch query body based on parameters"""
    filter_ = get_filter(reach, visited, user_sub, groups)

    if q == "*":
        logger.info("Performing match_all query")
        return {
            "bool": {
                "must": {"match_all": {}},
                "filter": {"bool": {"filter": filter_}},
            },
        }

    hybrid_search_enabled = check_hybrid_search_enabled()
    if hybrid_search_enabled:
        q_vector = embed_text(q)
    else:
        q_vector = None

    if not q_vector:
        logger.info("Performing full-text search without embedding: %s", q)
        return get_full_text_query(q, filter_)

    logger.info("Performing hybrid search with embedding: %s", q)
    return {
        "hybrid": {
            "queries": [
                get_full_text_query(q, filter_),
                get_semantic_search_query(q_vector, filter_, nb_results),
            ],
        }
    }

    logger.info("Performing hybrid search with embedding: %s", q)
    return {
        "hybrid": {
            "queries": [
                {
                    "bool": {
                        "must": get_full_text_query(q),
                        "filter": filter_,
                    }
                },
                {
                    "bool": {
                        "must": {
                            "knn": {
                                "embedding": {
                                    "vector": embedding,
                                    "k": nb_results,
                                }
                            }
                        },
                        "filter": filter_,
                    }
                },
            ]
        }
    }

def get_semantic_search_query(q_vector, filter_, nb_results):
    return {
        "bool": {
            "must": {
                "nested": {
                    "path": "chunks",
                    "score_mode": "max",
                    "query": {
                        "knn": {
                            "chunks.embedding": {
                                "vector": q_vector,
                                "k": nb_results,
                            }
                        }
                    },
                }
            },
            "filter": filter_,
        }
    }


def get_full_text_query(q, filter_):
    """Build OpenSearch full-text query"""
    return {
        "bool": {
            "must": {
                "bool":{
                    "should": [
                        {
                            "multi_match": {
                                "query": q,
                                "fields": [
                                    "title.*.text^3",
                                    "content.*",
                                ],
                            }
                        },
                        {
                            "multi_match": {
                                "query": q,
                                "fields": [
                                    "title.*.text.trigrams^3",
                                    "content.*.trigrams",
                                ],
                                "boost": settings.TRIGRAMS_BOOST,
                                "minimum_should_match": settings.TRIGRAMS_MINIMUM_SHOULD_MATCH,
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                },
            },
            "filter": filter,
        }
    }


def get_filter(reach, visited, user_sub, groups):
    """Build OpenSearch filter"""
    filters = [
        {"term": {"is_active": True}},  # filter out inactive documents
        # Access control filters
        {
            "bool": {
                "should": [
                    # Public or authenticated (not restricted)
                    {
                        "bool": {
                            "must_not": {
                                "term": {enums.REACH: enums.ReachEnum.RESTRICTED},
                            },
                            "must": {
                                "terms": {"_id": sorted(visited)},
                            },
                        }
                    },
                    # Restricted: either user or group must match
                    {"term": {enums.USERS: user_sub}},
                    {"terms": {enums.GROUPS: groups}},
                ],
                "minimum_should_match": 1,
            }
        },
    ]

    # Optional reach filter
    if reach is not None:
        filters.append({"term": {enums.REACH: reach}})

    return filters


def get_sort(query_keys, order_by, order_direction):
    """Build OpenSearch sort clause"""
    # Add sorting logic based on relevance or specified field
    if "hybrid" in query_keys:
        # sorting by other field than "_score" is not supported in hybrid search
        # see: https://github.com/opensearch-project/neural-search/issues/866
        return {"_score": {"order": order_direction}}
    if order_by == enums.RELEVANCE:
        return {"_score": {"order": order_direction}}

    return {order_by: {"order": order_direction}}


def get_params(query_keys):
    """Build OpenSearch search parameters"""
    if "hybrid" in query_keys:
        return {"search_pipeline": settings.HYBRID_SEARCH_PIPELINE_ID}
    return {}


def embed_document(document):
    """Get embedding vector for a given document"""
    return embed_text(format_document(document.title, document.content))


def chunk_document(title, content):
    """
    Chunk a document into multiple pieces.
    """
    chunks = [
        {
            'index': idx,
            'content': f"Title: {title}\n\n{chunked_content}",
            'embedding': embed_text(f"Title: {title}\n\n{chunked_content}")
        }
        for idx, chunked_content in enumerate(TEXT_SPLITTER.split_text(content))
    ]

    logger.info(f"Document '{title}' chunked into {len(chunks)} pieces")
    return chunks


def format_document(title, content):
    """Get the embedding input format for a document"""
    return f"<{title}>:<{content}>"


def embed_text(text):
    """
    Get embedding vector for the given text from any OpenAI-compatible embedding API
    """
    logger.info("embed: '%s'", text)

    response = requests.post(
        settings.EMBEDDING_API_PATH,
        headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}>"},
        json={
            "input": text,
            "model": settings.EMBEDDING_API_MODEL_NAME,
            "dimensions": settings.EMBEDDING_DIMENSION,
            "encoding_format": "float",
        },
        timeout=settings.EMBEDDING_REQUEST_TIMEOUT,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        logger.warning("embedding API request failed: %s", str(e))
        return None

    try:
        embedding = response.json()["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError):
        logger.warning("unexpected embedding response format: %s", response.text)
        return None

    return embedding


def prepare_document_for_indexing(document):
    """Prepare document for indexing using nested language structure and handle embedding"""

    language_code = detect_language_code(f"{document['title']} {document['content']}")
    return {
        "id": document["id"],
        f"title.{language_code}": document["title"],
        f"content.{language_code}": document["content"],
        "embedding_model": settings.EMBEDDING_API_MODEL_NAME
        if check_hybrid_search_enabled()
        else None,
        "chunks": chunk_document(
            document["title"], document["content"],
        ) 
        if check_hybrid_search_enabled()
        else None,
        "depth": document["depth"],
        "path": document["path"],
        "numchild": document["numchild"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
        "size": document["size"],
        "users": document["users"],
        "groups": document["groups"],
        "reach": document["reach"],
        "is_active": document["is_active"],
    }


def detect_language_code(text):
    """Detect the language code of the document content."""

    detected_code, confidence = LANGUAGE_IDENTIFIER.classify(text)

    if confidence < settings.LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD:
        return settings.UNDETERMINED_LANGUAGE_CODE

    return detected_code


def ensure_index_exists(index_name):
    """Create index if it does not exist"""
    try:
        opensearch_client().indices.get(index=index_name)
    except NotFoundError:
        logger.info("Creating index: %s", index_name)
        opensearch_client().indices.create(
            index=index_name,
            body={
                "settings": {
                    "index.knn": True,
                    "analysis": {
                        "analyzer": ANALYZERS,
                        "filter": FILTERS,
                    },
                },
                "mappings": MAPPINGS,
            },
        )


@cache
def check_hybrid_search_enabled():
    """Check that all required environment variables are set for hybrid search."""
    if settings.HYBRID_SEARCH_ENABLED is not True:
        logger.info("Hybrid search is disabled via HYBRID_SEARCH_ENABLED setting")
        return False

    required_vars = [
        "HYBRID_SEARCH_WEIGHTS",
        "EMBEDDING_API_PATH",
        "EMBEDDING_API_KEY",
        "EMBEDDING_API_MODEL_NAME",
        "EMBEDDING_DIMENSION",
    ]
    missing_vars = [var for var in required_vars if not getattr(settings, var, None)]
    if missing_vars:
        logger.warning(
            "Missing variables for hybrid search: %s", ", ".join(missing_vars)
        )
        return False

    return True
