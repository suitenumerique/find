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
    order_by,
    order_direction,
    search_indices,
    reach,
    visited,
    user_sub,
    groups,
    tags,
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
    q, nb_results, reach, visited, user_sub, groups, tags
):
    """Build OpenSearch query body based on parameters"""
    filter_ = get_filter(reach, visited, user_sub, groups, tags)

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


def get_filter(reach, visited, user_sub, groups, tags):
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
