"""Pydantic models for the structured query DSL."""

from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

UserQueryField = Literal[
    "id",
    "title",
    "content",
    "depth",
    "path",
    "numchild",
    "created_at",
    "updated_at",
    "size",
    "reach",
    "tags",
]

SystemQueryField = Literal["is_active", "users", "groups", "service"]

QueryField = Union[UserQueryField, SystemQueryField]


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


class FieldCondition[FieldT = UserQueryField](BaseModel):
    """A condition on a single field with an operator and value."""

    field: FieldT
    op: Operator
    value: Union[str, int, float, bool, List[str], List[int]]


class AndClause[FieldT = UserQueryField](BaseModel):
    """Logical AND of multiple where clauses."""

    model_config = ConfigDict(populate_by_name=True)
    and_: List["WhereClause[FieldT]"] = Field(alias="and")


class OrClause[FieldT = UserQueryField](BaseModel):
    """Logical OR of multiple where clauses."""

    model_config = ConfigDict(populate_by_name=True)
    or_: List["WhereClause[FieldT]"] = Field(alias="or")


class NotClause[FieldT = UserQueryField](BaseModel):
    """Logical NOT of a where clause."""

    model_config = ConfigDict(populate_by_name=True)
    not_: "WhereClause[FieldT]" = Field(alias="not")


type WhereClause[FieldT = UserQueryField] = Union[
    AndClause[FieldT], OrClause[FieldT], NotClause[FieldT], FieldCondition[FieldT]
]

AndClause.model_rebuild()
OrClause.model_rebuild()
NotClause.model_rebuild()


class SortClause(BaseModel):
    """Sort specification for search results."""

    field: Literal["relevance", "title", "created_at", "updated_at", "size"] = (
        "relevance"
    )
    direction: Literal["asc", "desc"] = "desc"


class SearchQuerySchema[FieldT = UserQueryField](BaseModel):
    """Top-level schema for structured search queries."""

    query: Optional[str] = None
    where: Optional[WhereClause[FieldT]] = None
    sort: Optional[List[SortClause]] = None
    limit: Optional[int] = Field(default=50, ge=1, le=100)
