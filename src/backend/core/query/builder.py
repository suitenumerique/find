"""Convert query DSL to OpenSearch queries."""

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

FIELD_MAPPING = {
    "id": "_id",
}


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
