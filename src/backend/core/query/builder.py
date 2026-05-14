"""Convert query DSL to OpenSearch queries."""

from typing import Optional

from opensearchpy import Q
from opensearchpy.helpers.query import Query

from ..schemas import (
    AndClause,
    FieldCondition,
    NotClause,
    Operator,
    OrClause,
    QueryField,
    WhereClause,
)

FIELD_MAPPING = {"id": "_id"}


def build_system_scope(
    user_sub: Optional[str] = None, service: Optional[str] = None
) -> WhereClause[QueryField]:
    """Build system-level access control filter.

    For user tokens: is_active AND service AND ((reach != restricted) OR (user in users))
    """
    filters: list[WhereClause[QueryField]] = [
        FieldCondition[QueryField](field="is_active", op=Operator.EQ, value=True)
    ]

    if service is not None:
        filters.append(
            FieldCondition[QueryField](field="service", op=Operator.EQ, value=service)
        )

    if user_sub is not None:
        user_in_users = FieldCondition[QueryField](
            field="users", op=Operator.IN, value=[user_sub]
        )
        not_restricted = NotClause[QueryField](
            not_=FieldCondition[QueryField](
                field="reach", op=Operator.EQ, value="restricted"
            )
        )
        reach_filter = OrClause[QueryField](or_=[not_restricted, user_in_users])
        filters.append(reach_filter)

    return AndClause[QueryField](and_=filters)


def combine_with_system_scope(
    user_where: Optional[WhereClause],
    user_sub: Optional[str],
    service: Optional[str] = None,
) -> WhereClause[QueryField]:
    """Combine user's where clause with system-level access control."""
    system_scope = build_system_scope(user_sub, service)

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

        case Operator.PREFIX if isinstance(value, str):
            return Q("prefix", **{field: value})

        case Operator.GT | Operator.GTE | Operator.LT | Operator.LTE:
            return Q("range", **{field: {op.value: value}})

        case Operator.EXISTS if isinstance(value, bool):
            return Q("exists", field=field) if value else ~Q("exists", field=field)

    raise ValueError(f"Invalid operator/value combination: {op} with {type(value)}")
