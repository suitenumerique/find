"""Opensearch related utils."""

import logging
from functools import cache

from django.conf import settings

import requests
from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from rest_framework.exceptions import ValidationError

from core import enums

logger = logging.getLogger(__name__)


HYBRID_SEARCH_PIPELINE_ID = "hybrid-search-pipeline"
REQUIRED_ENV_VARIABLES = [
    "OPENSEARCH_HOST",
    "OPENSEARCH_PORT",
    "OPENSEARCH_USER",
    "OPENSEARCH_PASSWORD",
    "OPENSEARCH_USE_SSL",
]


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
    page_number,
    page_size,
    k,
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
        q=q, k=k, reach=reach, visited=visited, user_sub=user_sub, groups=groups
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
            # Compute pagination parameters
            "from": (page_number - 1) * page_size,
            "size": page_size,
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
    q, k, reach, visited, user_sub, groups
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
        embedding = embed_text(q)
    else:
        embedding = None

    if not embedding:
        logger.info("Performing full-text search without embedding: %s", q)
        return {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": q,
                        # Give title more importance over content by a power of 3
                        "fields": ["title.text^3", "content"],
                    }
                },
                "filter": filter_,
            }
        }

    logger.info("Performing hybrid search with embedding: %s", q)
    return {
        "hybrid": {
            "queries": [
                {
                    "bool": {
                        "must": {
                            "multi_match": {
                                "query": q,
                                # Give title more importance over content by a power of 3
                                "fields": ["title.text^3", "content"],
                            }
                        },
                        "filter": filter_,
                    }
                },
                {
                    "bool": {
                        "must": {
                            "knn": {
                                "embedding": {
                                    "vector": embedding,
                                    "k": k,
                                }
                            }
                        },
                        "filter": filter_,
                    }
                },
            ]
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
        # sorting by other field than "_score" is not supported in hybird search
        # see: https://github.com/opensearch-project/neural-search/issues/866
        return {"_score": {"order": order_direction}}
    if order_by == enums.RELEVANCE:
        return {"_score": {"order": order_direction}}

    return {order_by: {"order": order_direction}}


def get_params(query_keys):
    """Build OpenSearch search parameters"""
    if "hybrid" in query_keys:
        ensure_search_pipeline_exists(HYBRID_SEARCH_PIPELINE_ID)
        return {"search_pipeline": HYBRID_SEARCH_PIPELINE_ID}
    return {}


def embed_document(document):
    """Get embedding vector for the given document"""
    return embed_text(f"<{document.title}>:<{document.content}>")


def embed_text(text):
    """Get embedding vector for the given text from the embedding API."""
    response = requests.post(
        settings.EMBEDDING_API_PATH,
        headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}>"},
        json={
            "input": text,
            "model": settings.EMBEDDING_API_MODEL_NAME,
            "dimensions": settings.EMBEDDING_DIMENSION,
            "encoding_format": "float",
        },
        timeout=10,
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


def ensure_index_exists(index_name):
    """Create index if it does not exist"""
    try:
        opensearch_client().indices.get(index=index_name)
    except NotFoundError:
        logger.info("Creating index: %s", index_name)
        opensearch_client().indices.create(
            index=index_name,
            body={
                "settings": {"index.knn": True},
                "mappings": {
                    "dynamic": "strict",
                    "properties": {
                        "id": {"type": "keyword"},
                        "title": {
                            "type": "keyword",
                            "fields": {"text": {"type": "text"}},
                        },
                        "depth": {"type": "integer"},
                        "path": {
                            "type": "keyword",
                            "fields": {"text": {"type": "text"}},
                        },
                        "numchild": {"type": "integer"},
                        "content": {"type": "text"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "size": {"type": "long"},
                        "users": {"type": "keyword"},
                        "groups": {"type": "keyword"},
                        "reach": {"type": "keyword"},
                        "is_active": {"type": "boolean"},
                        "embedding": {
                            # for simplicity, embedding is always present but is empty
                            # when hybrid search is disabled
                            "type": "knn_vector",
                            "dimension": settings.EMBEDDING_DIMENSION,
                            "method": {
                                "engine": "lucene",
                                "space_type": "l2",
                                "name": "hnsw",
                                "parameters": {},
                            },
                        },
                    },
                },
            },
        )


def ensure_search_pipeline_exists(pipeline_id):
    """Create search pipeline for hybrid search if it does not exist"""
    try:
        opensearch_client().search_pipeline.get(pipeline_id)
    except NotFoundError:
        logger.info("Creating search pipeline: %s", pipeline_id)
        opensearch_client().transport.perform_request(
            method="PUT",
            url="/_search/pipeline/" + pipeline_id,
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
