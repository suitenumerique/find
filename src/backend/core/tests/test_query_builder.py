"""Tests for the query builder module."""

import pytest

from core.query.builder import (
    build_filter,
    build_system_scope,
    combine_with_system_scope,
)
from core.schemas import (
    AndClause,
    FieldCondition,
    NotClause,
    Operator,
    OrClause,
    QueryField,
)


class TestFieldConditions:
    """Tests for build_filter() with FieldCondition inputs."""

    def test_eq_operator_string(self):
        """Test eq operator with string value."""
        condition = FieldCondition(field="reach", op=Operator.EQ, value="public")
        result = build_filter(condition)
        assert result.to_dict() == {"term": {"reach": "public"}}

    def test_eq_operator_boolean(self):
        """Test eq operator with boolean value."""
        condition = FieldCondition[QueryField](field="is_active", op=Operator.EQ, value=True)
        result = build_filter(condition)
        assert result.to_dict() == {"term": {"is_active": True}}

    def test_eq_operator_integer(self):
        """Test eq operator with integer value."""
        condition = FieldCondition(field="depth", op=Operator.EQ, value=3)
        result = build_filter(condition)
        assert result.to_dict() == {"term": {"depth": 3}}

    def test_in_operator(self):
        """Test in operator with list of strings."""
        condition = FieldCondition(field="tags", op=Operator.IN, value=["tag1", "tag2"])
        result = build_filter(condition)
        assert result.to_dict() == {"terms": {"tags": ["tag1", "tag2"]}}

    def test_all_operator(self):
        """Test all operator requires all values to match."""
        condition = FieldCondition(field="tags", op=Operator.ALL, value=["tag1", "tag2"])
        result = build_filter(condition)
        expected = {"bool": {"must": [{"term": {"tags": "tag1"}}, {"term": {"tags": "tag2"}}]}}
        assert result.to_dict() == expected

    def test_prefix_operator(self):
        """Test prefix operator."""
        condition = FieldCondition(field="path", op=Operator.PREFIX, value="/docs/")
        result = build_filter(condition)
        assert result.to_dict() == {"prefix": {"path": "/docs/"}}

    def test_gt_operator(self):
        """Test gt (greater than) operator."""
        condition = FieldCondition(field="size", op=Operator.GT, value=1000)
        result = build_filter(condition)
        assert result.to_dict() == {"range": {"size": {"gt": 1000}}}

    def test_gte_operator(self):
        """Test gte (greater than or equal) operator."""
        condition = FieldCondition(field="size", op=Operator.GTE, value=1000)
        result = build_filter(condition)
        assert result.to_dict() == {"range": {"size": {"gte": 1000}}}

    def test_lt_operator(self):
        """Test lt (less than) operator."""
        condition = FieldCondition(field="depth", op=Operator.LT, value=5)
        result = build_filter(condition)
        assert result.to_dict() == {"range": {"depth": {"lt": 5}}}

    def test_lte_operator(self):
        """Test lte (less than or equal) operator."""
        condition = FieldCondition(field="depth", op=Operator.LTE, value=5)
        result = build_filter(condition)
        assert result.to_dict() == {"range": {"depth": {"lte": 5}}}

    def test_exists_operator_true(self):
        """Test exists operator with true value."""
        condition = FieldCondition(field="tags", op=Operator.EXISTS, value=True)
        result = build_filter(condition)
        assert result.to_dict() == {"exists": {"field": "tags"}}

    def test_exists_operator_false(self):
        """Test exists operator with false value (must_not exists)."""
        condition = FieldCondition(field="tags", op=Operator.EXISTS, value=False)
        result = build_filter(condition)
        assert result.to_dict() == {"bool": {"must_not": [{"exists": {"field": "tags"}}]}}


class TestFieldMapping:
    """Tests for field name mapping (id -> _id)."""

    def test_id_field_mapped_to_underscore_id(self):
        """Test that 'id' field is mapped to '_id' in OpenSearch."""
        condition = FieldCondition(field="id", op=Operator.EQ, value="doc-123")
        result = build_filter(condition)
        assert result.to_dict() == {"term": {"_id": "doc-123"}}

    def test_id_field_with_in_operator(self):
        """Test that 'id' field mapping works with IN operator."""
        condition = FieldCondition(field="id", op=Operator.IN, value=["doc-1", "doc-2"])
        result = build_filter(condition)
        assert result.to_dict() == {"terms": {"_id": ["doc-1", "doc-2"]}}


class TestBooleanCombinators:
    """Tests for AND, OR, NOT clause handling."""

    def test_and_clause(self):
        """Test AND clause combines conditions with must."""
        clause = AndClause[QueryField](and_=[
            FieldCondition[QueryField](field="reach", op=Operator.EQ, value="public"),
            FieldCondition[QueryField](field="is_active", op=Operator.EQ, value=True),
        ])
        result = build_filter(clause)
        expected = {
            "bool": {
                "must": [
                    {"term": {"reach": "public"}},
                    {"term": {"is_active": True}},
                ]
            }
        }
        assert result.to_dict() == expected

    def test_and_clause_single_condition(self):
        """Test AND clause with single condition."""
        clause = AndClause(and_=[
            FieldCondition(field="reach", op=Operator.EQ, value="public"),
        ])
        result = build_filter(clause)
        expected = {"bool": {"must": [{"term": {"reach": "public"}}]}}
        assert result.to_dict() == expected

    def test_or_clause(self):
        """Test OR clause combines conditions with should."""
        clause = OrClause(or_=[
            FieldCondition(field="reach", op=Operator.EQ, value="public"),
            FieldCondition(field="reach", op=Operator.EQ, value="authenticated"),
        ])
        result = build_filter(clause)
        expected = {
            "bool": {
                "should": [
                    {"term": {"reach": "public"}},
                    {"term": {"reach": "authenticated"}},
                ],
                "minimum_should_match": 1,
            }
        }
        assert result.to_dict() == expected

    def test_or_clause_three_conditions(self):
        """Test OR clause with three conditions."""
        clause = OrClause(or_=[
            FieldCondition(field="reach", op=Operator.EQ, value="public"),
            FieldCondition(field="reach", op=Operator.EQ, value="authenticated"),
            FieldCondition(field="reach", op=Operator.EQ, value="restricted"),
        ])
        result = build_filter(clause)
        assert len(result.to_dict()["bool"]["should"]) == 3
        assert result.to_dict()["bool"]["minimum_should_match"] == 1

    def test_not_clause(self):
        """Test NOT clause wraps condition in must_not."""
        clause = NotClause(not_=FieldCondition(
            field="reach", op=Operator.EQ, value="restricted"
        ))
        result = build_filter(clause)
        expected = {"bool": {"must_not": [{"term": {"reach": "restricted"}}]}}
        assert result.to_dict() == expected


class TestNestedExpressions:
    """Tests for deeply nested boolean expressions."""

    def test_nested_and_or(self):
        """Test AND containing OR clauses."""
        clause = AndClause[QueryField](and_=[
            OrClause[QueryField](or_=[
                FieldCondition[QueryField](field="reach", op=Operator.EQ, value="public"),
                FieldCondition[QueryField](field="reach", op=Operator.EQ, value="authenticated"),
            ]),
            FieldCondition[QueryField](field="is_active", op=Operator.EQ, value=True),
        ])
        result = build_filter(clause)
        result_dict = result.to_dict()
        assert "bool" in result_dict
        assert "must" in result_dict["bool"]
        assert len(result_dict["bool"]["must"]) == 2
        assert "bool" in result_dict["bool"]["must"][0]
        assert "should" in result_dict["bool"]["must"][0]["bool"]

    def test_nested_or_and(self):
        """Test OR containing AND clauses."""
        clause = OrClause[QueryField](or_=[
            AndClause[QueryField](and_=[
                FieldCondition[QueryField](field="reach", op=Operator.EQ, value="public"),
                FieldCondition[QueryField](field="tags", op=Operator.IN, value=["important"]),
            ]),
            AndClause[QueryField](and_=[
                FieldCondition[QueryField](field="reach", op=Operator.EQ, value="authenticated"),
                FieldCondition[QueryField](field="is_active", op=Operator.EQ, value=True),
            ]),
        ])
        result = build_filter(clause)
        result_dict = result.to_dict()
        assert "bool" in result_dict
        assert "should" in result_dict["bool"]
        assert len(result_dict["bool"]["should"]) == 2

    def test_deeply_nested_expression(self):
        """Test deeply nested boolean expression."""
        clause = AndClause[QueryField](and_=[
            OrClause[QueryField](or_=[
                AndClause[QueryField](and_=[
                    FieldCondition[QueryField](field="reach", op=Operator.EQ, value="public"),
                    FieldCondition[QueryField](field="tags", op=Operator.IN, value=["important"]),
                ]),
                NotClause[QueryField](not_=FieldCondition[QueryField](
                    field="reach", op=Operator.EQ, value="restricted"
                )),
            ]),
            FieldCondition[QueryField](field="is_active", op=Operator.EQ, value=True),
        ])
        result = build_filter(clause)
        result_dict = result.to_dict()
        assert "bool" in result_dict
        assert "must" in result_dict["bool"]
        assert len(result_dict["bool"]["must"]) == 2

    def test_not_containing_and(self):
        """Test NOT clause containing AND clause."""
        clause = NotClause[QueryField](not_=AndClause[QueryField](and_=[
            FieldCondition[QueryField](field="reach", op=Operator.EQ, value="restricted"),
            FieldCondition[QueryField](field="is_active", op=Operator.EQ, value=False),
        ]))
        result = build_filter(clause)
        result_dict = result.to_dict()
        assert "bool" in result_dict
        assert "must_not" in result_dict["bool"]
        assert len(result_dict["bool"]["must_not"]) == 1
        assert "bool" in result_dict["bool"]["must_not"][0]


class TestSystemScope:
    """Tests for build_system_scope() and combine_with_system_scope()."""

    def test_build_system_scope_anonymous_no_service(self):
        result = build_system_scope(user_sub=None)
        assert isinstance(result, AndClause)
        assert len(result.and_) == 1
        assert result.and_[0].field == "is_active"

    def test_build_system_scope_anonymous_with_service(self):
        result = build_system_scope(user_sub=None, service="docs")
        assert isinstance(result, AndClause)
        assert len(result.and_) == 2
        assert result.and_[0].field == "is_active"
        assert result.and_[1].field == "service"
        assert result.and_[1].value == "docs"

    def test_build_system_scope_authenticated_with_service(self):
        result = build_system_scope(user_sub="user-123", service="wiki")
        assert isinstance(result, AndClause)
        assert len(result.and_) == 3
        assert result.and_[0].field == "is_active"
        assert result.and_[1].field == "service"
        assert result.and_[1].value == "wiki"
        assert isinstance(result.and_[2], OrClause)

    def test_build_system_scope_reach_filter_structure(self):
        result = build_system_scope(user_sub="user-123", service="docs")
        reach_filter = result.and_[2]
        assert isinstance(reach_filter, OrClause)
        assert len(reach_filter.or_) == 2
        assert isinstance(reach_filter.or_[0], NotClause)
        assert isinstance(reach_filter.or_[1], FieldCondition)
        assert reach_filter.or_[1].field == "users"

    def test_combine_with_system_scope_passes_service(self):
        result = combine_with_system_scope(
            user_where=None, user_sub="user-123", service="docs"
        )
        assert isinstance(result, AndClause)
        service_filter = result.and_[1]
        assert service_filter.field == "service"
        assert service_filter.value == "docs"

    def test_combine_with_system_scope_with_user_where(self):
        user_where = FieldCondition(field="tags", op=Operator.IN, value=["important"])
        result = combine_with_system_scope(
            user_where=user_where, user_sub="user-123", service="docs"
        )
        assert isinstance(result, AndClause)
        assert len(result.and_) == 2
        assert result.and_[0] == user_where

    def test_system_scope_builds_valid_opensearch_query(self):
        scope = build_system_scope(user_sub="user-123", service="docs")
        query = build_filter(scope)
        result_dict = query.to_dict()
        assert "bool" in result_dict
        assert "must" in result_dict["bool"]


class TestInvalidInput:
    """Tests for invalid operator/value combinations."""

    def test_in_operator_requires_list(self):
        """Test that IN operator with non-list value raises ValueError."""
        condition = FieldCondition(field="tags", op=Operator.IN, value="not-a-list")
        with pytest.raises(ValueError, match="Invalid operator/value combination"):
            build_filter(condition)

    def test_all_operator_requires_list(self):
        """Test that ALL operator with non-list value raises ValueError."""
        condition = FieldCondition(field="tags", op=Operator.ALL, value="not-a-list")
        with pytest.raises(ValueError, match="Invalid operator/value combination"):
            build_filter(condition)

    def test_in_operator_with_integer_raises(self):
        """Test that IN operator with integer value raises ValueError."""
        condition = FieldCondition(field="tags", op=Operator.IN, value=123)
        with pytest.raises(ValueError, match="Invalid operator/value combination"):
            build_filter(condition)

    def test_all_operator_with_boolean_raises(self):
        """Test that ALL operator with boolean value raises ValueError."""
        condition = FieldCondition(field="tags", op=Operator.ALL, value=True)
        with pytest.raises(ValueError, match="Invalid operator/value combination"):
            build_filter(condition)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_list_in_operator(self):
        """Test IN operator with empty list."""
        condition = FieldCondition(field="tags", op=Operator.IN, value=[])
        result = build_filter(condition)
        assert result.to_dict() == {"terms": {"tags": []}}

    def test_empty_list_all_operator(self):
        """Test ALL operator with empty list produces empty bool."""
        condition = FieldCondition(field="tags", op=Operator.ALL, value=[])
        result = build_filter(condition)
        assert result.to_dict() == {"bool": {}}

    def test_single_item_list_in_operator(self):
        """Test IN operator with single-item list."""
        condition = FieldCondition(field="tags", op=Operator.IN, value=["only-one"])
        result = build_filter(condition)
        assert result.to_dict() == {"terms": {"tags": ["only-one"]}}

    def test_single_item_list_all_operator(self):
        """Test ALL operator with single-item list."""
        condition = FieldCondition(field="tags", op=Operator.ALL, value=["only-one"])
        result = build_filter(condition)
        assert result.to_dict() == {"bool": {"must": [{"term": {"tags": "only-one"}}]}}

    def test_prefix_with_empty_string(self):
        """Test prefix operator with empty string."""
        condition = FieldCondition(field="path", op=Operator.PREFIX, value="")
        result = build_filter(condition)
        assert result.to_dict() == {"prefix": {"path": ""}}

    def test_range_with_zero(self):
        """Test range operators with zero value."""
        condition = FieldCondition(field="size", op=Operator.GTE, value=0)
        result = build_filter(condition)
        assert result.to_dict() == {"range": {"size": {"gte": 0}}}

    def test_range_with_negative(self):
        """Test range operators with negative value."""
        condition = FieldCondition(field="depth", op=Operator.GT, value=-1)
        result = build_filter(condition)
        assert result.to_dict() == {"range": {"depth": {"gt": -1}}}

    def test_in_operator_with_integer_list(self):
        """Test IN operator with list of integers."""
        condition = FieldCondition(field="depth", op=Operator.IN, value=[1, 2, 3])
        result = build_filter(condition)
        assert result.to_dict() == {"terms": {"depth": [1, 2, 3]}}
