"""Convert query DSL to OpenSearch queries."""

from typing import Optional

from opensearchpy import Q
from opensearchpy.helpers.query import Query

from .dsl import (
    AndClause,
    FieldCondition,
    NotClause,
    Operator,
    OrClause,
    WhereClause,
)

FIELD_MAPPING = {"id": "_id"}


def build_system_scope(user_sub: Optional[str] = None) -> WhereClause:
    """Build system-level access control filter.

    For user tokens: filters to active docs user can access via reach rules.
    For service tokens: filters to active docs only.

    Args:
        user_sub: User subject identifier. If None, builds filter for service token.

    Returns:
        WhereClause: Access control filter DSL.
    """
    is_active_filter = FieldCondition(field="is_active", op=Operator.EQ, value=True)

    if user_sub is None:
        # Service token: just is_active
        return AndClause(and_=[is_active_filter])

    # User token: is_active AND (restricted-with-access OR not-restricted)
    restricted_with_access = AndClause(
        and_=[
            FieldCondition(field="reach", op=Operator.EQ, value="restricted"),
            FieldCondition(field="users", op=Operator.IN, value=[user_sub]),
        ]
    )

    not_restricted = NotClause(
        not_=FieldCondition(field="reach", op=Operator.EQ, value="restricted")
    )

    reach_filter = OrClause(or_=[restricted_with_access, not_restricted])

    return AndClause(and_=[is_active_filter, reach_filter])


def combine_with_system_scope(
    user_where: Optional[WhereClause], user_sub: Optional[str]
) -> WhereClause:
    """Combine user's where clause with system-level access control."""
    system_scope = build_system_scope(user_sub)

    if user_where is None:
        return system_scope

    return AndClause(and_=[user_where, system_scope])


def build_filter(where: WhereClause) -> Query:
    """Convert a WhereClause DSL tree into an OpenSearch Query object."""
    if isinstance(where, AndClause):
        return Q("bool", must=[build_filter(c) for c in where.and_])

    if isinstance(where, OrClause):
        return Q(
            "bool",
            should=[build_filter(c) for c in where.or_],
            minimum_should_match=1,
        )

    if isinstance(where, NotClause):
        return Q("bool", must_not=[build_filter(where.not_)])

    return _build_field_condition(where)


def _build_field_condition(condition: FieldCondition) -> Query:
    field = FIELD_MAPPING.get(condition.field, condition.field)
    op = condition.op
    value = condition.value

    match op:
        case Operator.EQ:
            return Q("term", **{field: value})

        case Operator.IN | Operator.ALL if isinstance(value, list):
            if op == Operator.IN:
                return Q("terms", **{field: value})
            return Q("bool", must=[Q("term", **{field: v}) for v in value])

        case Operator.PREFIX:
            return Q("prefix", **{field: value})

        case Operator.GT | Operator.GTE | Operator.LT | Operator.LTE:
            return Q("range", **{field: {op.value: value}})

        case Operator.EXISTS:
            q = Q("exists", field=field)
            return q if value else ~q

    raise ValueError(f"Invalid operator/value combination: {op} with {type(value)}")
