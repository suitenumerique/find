"""OpenSearch search utilities."""

import logging

from django.conf import settings

from core import enums

from .opensearch import opensearch_client

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
):
    """Perform an OpenSearch search"""
    query = get_query(
        q=q,
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
            "sort": get_sort(
                order_by=order_by,
                order_direction=order_direction,
            ),
            "size": nb_results,
            "query": query,
        },
        # disable=unexpected-keyword-arg because
        # ignore_unavailable is not in the method declaration
        ignore_unavailable=True,
    )


# pylint: disable=too-many-arguments, too-many-positional-arguments
def get_query(  # noqa : PLR0913
    q,
    reach,
    visited,
    user_sub,
    groups,
    tags,
    path=None,
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

    logger.info("Performing full-text search: %s", q)
    return get_full_text_query(q, filter_)


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


def get_sort(order_by, order_direction):
    """Build OpenSearch sort clause"""
    if order_by == enums.RELEVANCE:
        return {"_score": {"order": order_direction}}

    return {order_by: {"order": order_direction}}
