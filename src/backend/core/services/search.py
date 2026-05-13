"""OpenSearch search utilities."""

import logging

from django.conf import settings

from opensearchpy import Q

from core import enums
from core.query.builder import build_filter
from core.query.dsl import SearchQuerySchema, WhereClause

from .opensearch import opensearch_client

logger = logging.getLogger(__name__)


def search(params: SearchQuerySchema, search_indices: list[str]) -> dict[str, object]:
    """Perform an OpenSearch search using DSL parameters."""
    query_text = params.query or "*"
    where_clause: WhereClause | None = params.where
    filter_query = build_filter(where_clause) if where_clause else None

    if query_text == "*":
        logger.info("Performing match_all query")
        if filter_query:
            opensearch_query = Q("bool", must=Q("match_all"), filter=filter_query)
        else:
            opensearch_query = Q("match_all")
    else:
        logger.info("Performing full-text search: %s", query_text)
        opensearch_query = get_full_text_query(query_text, filter_query)

    sort_clauses = []
    if params.sort:
        for s in params.sort:
            sort_clauses.append(get_sort(s.field, s.direction))
    else:
        sort_clauses.append(get_sort("relevance", "desc"))

    return opensearch_client().search(  # pylint: disable=unexpected-keyword-arg
        index=",".join(search_indices),
        body={
            "_source": enums.SOURCE_FIELDS,
            "script_fields": {
                "number_of_users": {"script": {"source": "doc['users'].size()"}},
                "number_of_groups": {"script": {"source": "doc['groups'].size()"}},
            },
            "sort": [s.to_dict() for s in sort_clauses],
            "size": params.limit or 50,
            "query": opensearch_query.to_dict(),
        },
        ignore_unavailable=True,
    )


def get_full_text_query(query: str, filter_query) -> Q:  # type: ignore[valid-type]
    """Build OpenSearch full-text query."""
    multi_match_standard = Q(
        "multi_match",
        query=query,
        fields=[
            "title.*.text^3",
            "content.*",
        ],
    )
    multi_match_trigram = Q(
        "multi_match",
        query=query,
        fields=[
            "title.*.text.trigrams^3",
            "content.*.trigrams",
        ],
        boost=settings.TRIGRAMS_BOOST,
        minimum_should_match=settings.TRIGRAMS_MINIMUM_SHOULD_MATCH,
    )

    inner_bool = Q(
        "bool",
        should=[multi_match_standard, multi_match_trigram],
        minimum_should_match=1,
    )

    if filter_query:
        return Q("bool", must=inner_bool, filter=filter_query)
    return Q("bool", must=inner_bool)


class SortSpec:
    """Sort specification wrapper for OpenSearch sort clauses."""

    def __init__(self, field: str, order: str = "desc"):
        self.field = field
        self.order = order

    def to_dict(self) -> dict[str, dict[str, str]]:
        """Convert to OpenSearch sort dict format."""
        return {self.field: {"order": self.order}}


def get_sort(field: str, direction: str) -> SortSpec:
    """Build OpenSearch sort clause from field and direction."""
    if field == "relevance":
        return SortSpec("_score", direction)
    return SortSpec(field, direction)
