"""Tests for the query DSL builder converting to OpenSearch queries."""

import pytest

from core.query.builder import build_filter
from core.query.dsl import (
    AndClause,
    FieldCondition,
    NotClause,
    Operator,
    OrClause,
)


class TestFieldConditions:
    """Tests for individual field condition operators."""

    def test_eq_operator(self):
        """The eq operator should produce a term query."""
        condition = FieldCondition(field="reach", op=Operator.EQ, value="public")
        assert build_filter(condition).to_dict() == {"term": {"reach": "public"}}

    def test_eq_operator_boolean(self):
        """The eq operator should handle boolean values."""
        condition = FieldCondition(field="is_active", op=Operator.EQ, value=True)
        assert build_filter(condition).to_dict() == {"term": {"is_active": True}}

    def test_in_operator(self):
        """The in operator should produce a terms query."""
        condition = FieldCondition(
            field="tags", op=Operator.IN, value=["finance", "legal"]
        )
        assert build_filter(condition).to_dict() == {
            "terms": {"tags": ["finance", "legal"]}
        }

    def test_all_operator(self):
        """The all operator should require all values via bool must."""
        condition = FieldCondition(
            field="tags", op=Operator.ALL, value=["finance", "approved"]
        )
        assert build_filter(condition).to_dict() == {
            "bool": {
                "must": [
                    {"term": {"tags": "finance"}},
                    {"term": {"tags": "approved"}},
                ]
            }
        }

    def test_prefix_operator(self):
        """The prefix operator should produce a prefix query."""
        condition = FieldCondition(
            field="path", op=Operator.PREFIX, value="/teams/finance"
        )
        assert build_filter(condition).to_dict() == {
            "prefix": {"path": "/teams/finance"}
        }

    def test_gt_operator(self):
        """The gt operator should produce a range query with gt."""
        condition = FieldCondition(field="size", op=Operator.GT, value=1000)
        assert build_filter(condition).to_dict() == {"range": {"size": {"gt": 1000}}}

    def test_gte_operator(self):
        """The gte operator should produce a range query with gte."""
        condition = FieldCondition(
            field="created_at", op=Operator.GTE, value="2024-01-01"
        )
        assert build_filter(condition).to_dict() == {
            "range": {"created_at": {"gte": "2024-01-01"}}
        }

    def test_lt_operator(self):
        """The lt operator should produce a range query with lt."""
        condition = FieldCondition(field="size", op=Operator.LT, value=5000)
        assert build_filter(condition).to_dict() == {"range": {"size": {"lt": 5000}}}

    def test_lte_operator(self):
        """The lte operator should produce a range query with lte."""
        condition = FieldCondition(
            field="updated_at", op=Operator.LTE, value="2024-12-31"
        )
        assert build_filter(condition).to_dict() == {
            "range": {"updated_at": {"lte": "2024-12-31"}}
        }

    def test_exists_operator_true(self):
        """The exists operator with true should check field existence."""
        condition = FieldCondition(field="tags", op=Operator.EXISTS, value=True)
        assert build_filter(condition).to_dict() == {"exists": {"field": "tags"}}

    def test_exists_operator_false(self):
        """The exists operator with false should negate field existence."""
        condition = FieldCondition(field="tags", op=Operator.EXISTS, value=False)
        assert build_filter(condition).to_dict() == {
            "bool": {"must_not": [{"exists": {"field": "tags"}}]}
        }


class TestFieldMapping:
    """Tests for field name mapping (e.g., id -> _id)."""

    def test_id_maps_to_underscore_id(self):
        """The id field should be mapped to _id for OpenSearch."""
        condition = FieldCondition(field="id", op=Operator.IN, value=["doc-1", "doc-2"])
        assert build_filter(condition).to_dict() == {
            "terms": {"_id": ["doc-1", "doc-2"]}
        }

    def test_unmapped_field_passes_through(self):
        """Unmapped fields should pass through unchanged."""
        condition = FieldCondition(field="custom_field", op=Operator.EQ, value="test")
        assert build_filter(condition).to_dict() == {"term": {"custom_field": "test"}}


class TestBooleanCombinators:
    """Tests for AND, OR, NOT boolean combinators."""

    def test_and_clause(self):
        """The and clause should produce a bool must query."""
        clause = AndClause(
            and_=[
                FieldCondition(field="reach", op=Operator.EQ, value="public"),
                FieldCondition(field="is_active", op=Operator.EQ, value=True),
            ]
        )
        assert build_filter(clause).to_dict() == {
            "bool": {
                "must": [
                    {"term": {"reach": "public"}},
                    {"term": {"is_active": True}},
                ]
            }
        }

    def test_or_clause(self):
        """The or clause should produce a bool should query."""
        clause = OrClause(
            or_=[
                FieldCondition(field="reach", op=Operator.EQ, value="public"),
                FieldCondition(field="reach", op=Operator.EQ, value="authenticated"),
            ]
        )
        assert build_filter(clause).to_dict() == {
            "bool": {
                "should": [
                    {"term": {"reach": "public"}},
                    {"term": {"reach": "authenticated"}},
                ],
                "minimum_should_match": 1,
            }
        }

    def test_not_clause(self):
        """The not clause should produce a bool must_not query."""
        clause = NotClause(
            not_=FieldCondition(field="tags", op=Operator.IN, value=["draft"])
        )
        assert build_filter(clause).to_dict() == {
            "bool": {"must_not": [{"terms": {"tags": ["draft"]}}]}
        }


class TestNestedExpressions:
    """Tests for deeply nested boolean expressions."""

    def test_and_with_nested_or(self):
        """An and clause should support nested or clauses."""
        clause = AndClause(
            and_=[
                FieldCondition(field="reach", op=Operator.EQ, value="restricted"),
                OrClause(
                    or_=[
                        FieldCondition(field="tags", op=Operator.IN, value=["finance"]),
                        FieldCondition(
                            field="path", op=Operator.PREFIX, value="/teams/legal"
                        ),
                    ]
                ),
            ]
        )
        assert build_filter(clause).to_dict() == {
            "bool": {
                "must": [
                    {"term": {"reach": "restricted"}},
                    {
                        "bool": {
                            "should": [
                                {"terms": {"tags": ["finance"]}},
                                {"prefix": {"path": "/teams/legal"}},
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                ]
            }
        }

    def test_and_with_nested_not(self):
        """An and clause should support nested not clauses."""
        clause = AndClause(
            and_=[
                FieldCondition(field="reach", op=Operator.EQ, value="public"),
                NotClause(
                    not_=FieldCondition(
                        field="tags", op=Operator.IN, value=["archived"]
                    )
                ),
            ]
        )
        assert build_filter(clause).to_dict() == {
            "bool": {
                "must": [
                    {"term": {"reach": "public"}},
                    {"bool": {"must_not": [{"terms": {"tags": ["archived"]}}]}},
                ]
            }
        }

    def test_deeply_nested_expression(self):
        """Deeply nested boolean expressions should be handled correctly."""
        clause = AndClause(
            and_=[
                FieldCondition(field="is_active", op=Operator.EQ, value=True),
                OrClause(
                    or_=[
                        AndClause(
                            and_=[
                                FieldCondition(
                                    field="tags",
                                    op=Operator.ALL,
                                    value=["finance", "approved"],
                                ),
                                FieldCondition(
                                    field="path",
                                    op=Operator.PREFIX,
                                    value="/teams/finance",
                                ),
                            ]
                        ),
                        AndClause(
                            and_=[
                                FieldCondition(
                                    field="tags", op=Operator.IN, value=["legal"]
                                ),
                                NotClause(
                                    not_=FieldCondition(
                                        field="tags", op=Operator.IN, value=["draft"]
                                    )
                                ),
                            ]
                        ),
                    ]
                ),
            ]
        )
        assert build_filter(clause).to_dict() == {
            "bool": {
                "must": [
                    {"term": {"is_active": True}},
                    {
                        "bool": {
                            "should": [
                                {
                                    "bool": {
                                        "must": [
                                            {
                                                "bool": {
                                                    "must": [
                                                        {"term": {"tags": "finance"}},
                                                        {"term": {"tags": "approved"}},
                                                    ]
                                                }
                                            },
                                            {"prefix": {"path": "/teams/finance"}},
                                        ]
                                    }
                                },
                                {
                                    "bool": {
                                        "must": [
                                            {"terms": {"tags": ["legal"]}},
                                            {
                                                "bool": {
                                                    "must_not": [
                                                        {"terms": {"tags": ["draft"]}}
                                                    ]
                                                }
                                            },
                                        ]
                                    }
                                },
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                ]
            }
        }


class TestInvalidInput:
    """Tests for error handling on invalid operator/value combinations."""

    def test_in_operator_with_non_list_raises(self):
        """The in operator should raise ValueError for non-list values."""
        condition = FieldCondition(field="tags", op=Operator.IN, value="not-a-list")
        with pytest.raises(ValueError, match="Invalid operator/value combination"):
            build_filter(condition)

    def test_all_operator_with_non_list_raises(self):
        """The all operator should raise ValueError for non-list values."""
        condition = FieldCondition(field="tags", op=Operator.ALL, value="not-a-list")
        with pytest.raises(ValueError, match="Invalid operator/value combination"):
            build_filter(condition)
