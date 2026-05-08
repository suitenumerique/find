"""Pydantic models for the structured query DSL."""

from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BLOCKED_FIELDS = frozenset({"users", "groups", "is_active"})


class Operator(str, Enum):
    """Supported filter operators for field conditions."""

    EQ = "eq"
    IN = "in"
    ALL = "all"
    PREFIX = "prefix"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EXISTS = "exists"


class FieldCondition(BaseModel):
    """A single field condition with operator and value."""

    field: str
    op: Operator
    value: Union[str, int, float, bool, List[str], List[int]]


class AndClause(BaseModel):
    """Logical AND combinator for multiple where clauses."""

    model_config = ConfigDict(populate_by_name=True)
    and_: List["WhereClause"] = Field(alias="and")


class OrClause(BaseModel):
    """Logical OR combinator for multiple where clauses."""

    model_config = ConfigDict(populate_by_name=True)
    or_: List["WhereClause"] = Field(alias="or")


class NotClause(BaseModel):
    """Logical NOT combinator for a single where clause."""

    model_config = ConfigDict(populate_by_name=True)
    not_: "WhereClause" = Field(alias="not")


WhereClause = Union[AndClause, OrClause, NotClause, FieldCondition]

# Pydantic requires rebuild() for recursive forward references
AndClause.model_rebuild()
OrClause.model_rebuild()
NotClause.model_rebuild()


class SortClause(BaseModel):
    """Sort specification for search results."""

    field: Literal["relevance", "title", "created_at", "updated_at", "size"] = (
        "relevance"
    )
    direction: Literal["asc", "desc"] = "desc"


class SearchQuerySchema(BaseModel):
    """Top-level schema for structured search queries."""

    query: str
    where: Optional[WhereClause] = None
    sort: Optional[List[SortClause]] = None
    limit: Optional[int] = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_where_clause(self) -> "SearchQuerySchema":
        """Reject security-sensitive fields in user-provided where clause."""
        if self.where is not None:
            _check_blocked_fields(self.where)
        return self


def _check_blocked_fields(clause: WhereClause) -> None:
    if isinstance(clause, AndClause):
        for c in clause.and_:
            _check_blocked_fields(c)
    elif isinstance(clause, OrClause):
        for c in clause.or_:
            _check_blocked_fields(c)
    elif isinstance(clause, NotClause):
        _check_blocked_fields(clause.not_)
    elif isinstance(clause, FieldCondition) and clause.field in BLOCKED_FIELDS:
        raise ValueError(f"Field '{clause.field}' is not allowed in where clauses")
