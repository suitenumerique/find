"""OpenSearch search utilities."""

import logging

from django.conf import settings

from core import enums

from .embedding import embed_text
from .opensearch import check_hybrid_search_enabled, opensearch_client

logger = logging.getLogger(__name__)


# pylint: disable=too-many-arguments, too-many-positional-arguments
def search(  # noqa : PLR0913
    q,
    nb_results,
    search_indices,
    reach,
    visited,
    user_sub,
    groups,
    tags,
    path=None,
    enable_rescore=True,
):
    """Perform an OpenSearch search"""
    query = get_query(
        q=q,
        nb_results=nb_results,
        reach=reach,
        visited=visited,
        user_sub=user_sub,
        groups=groups,
        tags=tags,
        path=path,
    )
    return opensearch_client().search(  # pylint: disable=unexpected-keyword-arg
        index=",".join(search_indices),
        body={
            "_source": enums.SOURCE_FIELDS,  # limit the fields to return
            "script_fields": {
                "number_of_users": {"script": {"source": "doc['users'].size()"}},
                "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
            },
            "size": nb_results,
            "query": query,
            "rescore": get_rescore(nb_results=nb_results) if enable_rescore else [],
        },
        params=get_params(query_keys=query.keys()),
        # disable=unexpected-keyword-arg because
        # ignore_unavailable is not in the method declaration
        ignore_unavailable=True,
    )


# pylint: disable=too-many-arguments, too-many-positional-arguments
def get_query(  # noqa : PLR0913
    q, nb_results, reach, visited, user_sub, groups, tags, path=None
):
    """Build OpenSearch query body based on parameters"""
    filter_ = get_filter(reach, visited, user_sub, groups, tags, path)

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


def get_semantic_search_query(q_vector, filter_, nb_results):
    """Build OpenSearch semantic search query"""
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
                "bool": {
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
            "filter": filter_,
        }
    }


# pylint: disable=too-many-arguments, too-many-positional-arguments
def get_filter(  # noqa : PLR0913
    reach, visited, user_sub, groups, tags, path=None
):
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

    # Optional tags filter
    if tags:
        # logical or: if tags are provided the matching documents should have at least one of them
        filters.append({"terms": {"tags": tags}})

    # Optional path filter
    if path:
        # filter documents that start with the provided path
        filters.append({"prefix": {"path": path}})

    return filters


def get_rescore(nb_results):
    """
    Build rescore query.
    rescore includes:
        - a decay function on the `updated_at` field to boost more recently updated documents
    """
    return [
        {
            "window_size": nb_results,
            "query": {
                "rescore_query_weight": settings.RESCORE_UPDATED_AT_WEIGHT,
                "rescore_query": {
                    "function_score": {
                        "functions": [
                            {
                                "gauss": {
                                    "updated_at": {
                                        "origin": "now",
                                        "offset": settings.RESCORE_UPDATED_AT_OFFSET,
                                        "scale": settings.RESCORE_UPDATED_AT_SCALE,
                                        "decay": settings.RESCORE_UPDATED_AT_DECAY,
                                    }
                                }
                            }
                        ],
                    }
                },
            },
        }
    ]


def get_params(query_keys):
    """Build OpenSearch search parameters"""
    if "hybrid" in query_keys:
        return {"search_pipeline": settings.HYBRID_SEARCH_PIPELINE_ID}
    return {}
