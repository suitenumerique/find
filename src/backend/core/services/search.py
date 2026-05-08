"""OpenSearch search utilities."""

import logging
from dataclasses import dataclass

from django.conf import settings

from opensearchpy import Q

from core import enums

from .opensearch import opensearch_client

logger = logging.getLogger(__name__)


@dataclass
class SortSpec:
    """Sort specification - DSL-like wrapper for OpenSearch sort clauses."""

    field: str
    order: str = "desc"

    def to_dict(self) -> dict[str, dict[str, str]]:
        """Convert to OpenSearch sort dict format."""
        return {self.field: {"order": self.order}}


# pylint: disable=too-many-arguments, too-many-positional-arguments
def search(  # noqa : PLR0913
    query: str,
    nb_results: int,
    order_by: str,
    order_direction: str,
    search_indices: list[str],
    reach: str | None,
    visited: list[str],
    user_sub: str,
    groups: list[str],
    tags: list[str],
    path: str | None = None,
) -> dict[str, object]:
    """Perform an OpenSearch search"""
    opensearch_query = get_query(
        query=query,
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
            ).to_dict(),
            "size": nb_results,
            "query": opensearch_query.to_dict(),
        },
        # disable=unexpected-keyword-arg because
        # ignore_unavailable is not in the method declaration
        ignore_unavailable=True,
    )


# pylint: disable=too-many-arguments, too-many-positional-arguments
def get_query(  # noqa : PLR0913
    query: str,
    reach: str | None,
    visited: list[str],
    user_sub: str,
    groups: list[str],
    tags: list[str],
    path: str | None = None,
) -> Q:
    """Build OpenSearch query body based on parameters."""
    filter_ = get_filter(reach, visited, user_sub, groups, tags, path)

    if query == "*":
        logger.info("Performing match_all query")
        return Q("bool", must=Q("match_all"), filter=Q("bool", filter=filter_))

    logger.info("Performing full-text search: %s", query)
    return get_full_text_query(query, filter_)


def get_full_text_query(query: str, filter_: list[Q]) -> Q:
    """Build OpenSearch full-text query"""
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

    return Q("bool", must=inner_bool, filter=filter_)


# pylint: disable=too-many-arguments, too-many-positional-arguments
def get_filter(  # noqa : PLR0913
    reach: str | None,
    visited: list[str],
    user_sub: str,
    groups: list[str],
    tags: list[str],
    path: str | None = None,
) -> list[Q]:
    """Build OpenSearch filter using Q objects.

    Returns a list of Q filter objects for use in OpenSearch bool query filter context.
    """
    # Filter out inactive documents
    is_active_filter = Q("term", is_active=True)

    # Access control filters - THREE paths for document access:
    # Path 1: Public/authenticated docs (not restricted) that user has visited
    visited_non_restricted = Q(
        "bool",
        must_not=Q("term", **{enums.REACH: enums.ReachEnum.RESTRICTED}),
        must=Q("terms", _id=sorted(visited)),
    )
    # Path 2: Restricted docs where user is explicitly listed
    user_match = Q("term", **{enums.USERS: user_sub})
    # Path 3: Restricted docs where user's group is listed
    group_match = Q("terms", **{enums.GROUPS: groups})

    access_control_filter = Q(
        "bool",
        should=[visited_non_restricted, user_match, group_match],
        minimum_should_match=1,
    )

    filters: list[Q] = [is_active_filter, access_control_filter]

    # Optional reach filter
    if reach is not None:
        filters.append(Q("term", **{enums.REACH: reach}))

    # Optional tags filter
    if tags:
        filters.append(Q("terms", tags=tags))

    # Optional path filter
    if path:
        filters.append(Q("prefix", path=path))

    return filters


def get_sort(order_by: str, order_direction: str) -> SortSpec:
    """Build OpenSearch sort clause."""
    if order_by == enums.RELEVANCE:
        return SortSpec("_score", order_direction)
    return SortSpec(order_by, order_direction)
