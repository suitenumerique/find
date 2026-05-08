"""OpenSearch search utilities."""

import logging
from typing import List

from django.conf import settings

from core import enums
from core.query.builder import build_filter
from core.query.dsl import SearchQuerySchema, WhereClause

from .opensearch import opensearch_client

logger = logging.getLogger(__name__)


def search(params: SearchQuerySchema, search_indices: List[str]):
    """Perform an OpenSearch search.

    Args:
        params: SearchQuerySchema with query, where (combined with SystemScope),
                sort, and limit fields.
        search_indices: List of index names to search.
    """
    q = params.query
    where = params.where
    nb_results = params.limit or 50
    order_by = params.sort[0].field if params.sort else "relevance"
    order_direction = params.sort[0].direction if params.sort else "desc"

    query = get_query(q=q, where=where)
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


def get_query(q, where: WhereClause):
    """Build OpenSearch query body."""
    filter_ = build_filter(where).to_dict()

    if q == "*":
        logger.info("Performing match_all query")
        return {
            "bool": {
                "must": {"match_all": {}},
                "filter": filter_,
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


def get_sort(order_by, order_direction):
    """Build OpenSearch sort clause"""
    if order_by == enums.RELEVANCE:
        return {"_score": {"order": order_direction}}

    return {order_by: {"order": order_direction}}
