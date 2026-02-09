"""OpenSearch search utilities."""

import logging

from django.conf import settings

from core import enums
from core.enums import SearchTypeEnum

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
    path=None,
    search_type=None,
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
        search_type=search_type,
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
            "query": query,
        },
        params=get_params(query_keys=query.keys()),
        # disable=unexpected-keyword-arg because
        # ignore_unavailable is not in the method declaration
        ignore_unavailable=True,
    )


# pylint: disable=too-many-arguments, too-many-positional-arguments
def get_query(  # noqa : PLR0913
    q, nb_results, reach, visited, user_sub, groups, tags, path=None, search_type=None
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

    q_vector = vectorize_query(q, search_type)

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

def vectorize_query(q, search_type=None):
    """Vectorize the query if hybrid search is enabled and requested"""
    hybrid_search_enabled = check_hybrid_search_enabled()

    if hybrid_search_enabled and (search_type == SearchTypeEnum.HYBRID or search_type is None):
        q_vector = embed_text(q)
    else:
        if hybrid_search_enabled and search_type != SearchTypeEnum.HYBRID:
            logger.info(
                "Hybrid search is enabled but was disabled by request (search_type=%s)",
                search_type.value,
            )
        if not hybrid_search_enabled and search_type == SearchTypeEnum.HYBRID:
            logger.warning(
                "Hybrid search was requested (search_type=hybrid) but is disabled on server",
            )
        q_vector = None

    return q_vector


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
