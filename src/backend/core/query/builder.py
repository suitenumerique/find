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
    QueryField,
    WhereClause,
)

FIELD_MAPPING = {"id": "_id"}


def build_system_scope(user_sub: Optional[str] = None) -> WhereClause[QueryField]:
    """Build system-level access control filter."""
    is_active = FieldCondition[QueryField](
        field="is_active", op=Operator.EQ, value=True
    )

    if user_sub is None:
        return AndClause[QueryField](and_=[is_active])

    restricted_with_access = AndClause[QueryField](
        and_=[
            FieldCondition[QueryField](
                field="reach", op=Operator.EQ, value="restricted"
            ),
            FieldCondition[QueryField](field="users", op=Operator.IN, value=[user_sub]),
        ]
    )

    not_restricted = NotClause[QueryField](
        not_=FieldCondition[QueryField](
            field="reach", op=Operator.EQ, value="restricted"
        )
    )

    reach_filter = OrClause[QueryField](or_=[restricted_with_access, not_restricted])

    return AndClause[QueryField](and_=[is_active, reach_filter])


def combine_with_system_scope(
    user_where: Optional[WhereClause], user_sub: Optional[str]
) -> WhereClause[QueryField]:
    """Combine user's where clause with system-level access control."""
    system_scope = build_system_scope(user_sub)

    if user_where is None:
        return system_scope

    return AndClause[QueryField](and_=[user_where, system_scope])  # type: ignore[list-item]


def build_filter(where: WhereClause[QueryField]) -> Query:
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


def _build_field_condition(condition: FieldCondition[QueryField]) -> Query:
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
