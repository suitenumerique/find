"""msgspec-based schemas for high-performance serialization."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Generic, List, Literal, Optional, TypeVar, Union
from uuid import UUID

import msgspec
from django.utils import timezone
from django.utils.text import slugify
from msgspec import Meta, Struct, field
from msgspec.structs import force_setattr

from . import enums


AwareDatetime = Annotated[datetime, Meta(tz=True)]


class Document(Struct):
    """Schema for validating the documents submitted to our API for indexing"""

    id: UUID
    title: Annotated[str, Meta(max_length=300)]
    depth: Annotated[int, Meta(ge=0)]
    path: Annotated[str, Meta(max_length=300)]
    numchild: Annotated[int, Meta(ge=0)]
    content: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    size: Annotated[int, Meta(ge=0, le=100 * 1024**3)]
    is_active: bool
    users: List[Annotated[str, Meta(max_length=50)]] = []
    groups: List[Annotated[str, Meta(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]] = []
    reach: Optional[enums.ReachEnum] = enums.ReachEnum.RESTRICTED
    tags: List[Annotated[str, Meta(max_length=100)]] = []

    def __post_init__(self):
        force_setattr(self, "title", self.title.strip().lower())

        now = timezone.now()
        if self.created_at >= now:
            raise ValueError("created_at must be earlier than now")
        if self.updated_at >= now:
            raise ValueError("updated_at must be earlier than now")

        if self.created_at > self.updated_at:
            raise ValueError("updated_at must be later than created_at")

        if not self.title and not self.content:
            raise ValueError("Either title or content should have at least 1 character")

        for group in self.groups:
            slug = slugify(group)
            if group != slug:
                raise ValueError(
                    f"Groups must be slugs (lowercase, hyphen-separated): {slug}"
                )


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

# Type variable for generic field types
FieldT = TypeVar("FieldT")


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


class FieldCondition(Struct, Generic[FieldT]):
    """A condition on a single field with an operator and value."""

    field: FieldT
    op: Operator
    value: Union[str, int, float, bool, list[Union[str, int]]]


class AndClause(Struct, Generic[FieldT]):
    """Logical AND of multiple where clauses."""

    and_: list["WhereClause[FieldT]"] = field(name="and")


class OrClause(Struct, Generic[FieldT]):
    """Logical OR of multiple where clauses."""

    or_: list["WhereClause[FieldT]"] = field(name="or")


class NotClause(Struct, Generic[FieldT]):
    """Logical NOT of a where clause."""

    not_: "WhereClause[FieldT]" = field(name="not")


# Type alias for where clause union (for type hints and encoding)
WhereClause = Union[
    AndClause[FieldT], OrClause[FieldT], NotClause[FieldT], FieldCondition[FieldT]
]

# Raw dict type for decoding (msgspec can't discriminate struct unions by field presence)
WhereClauseDict = dict


class SortClause(Struct):
    """Sort specification for search results."""

    field: Literal["relevance", "title", "created_at", "updated_at", "size"] = (
        "relevance"
    )
    direction: Literal["asc", "desc"] = "desc"


class SearchQuerySchema(Struct, Generic[FieldT]):
    """Top-level schema for structured search queries (API input).

    Note: `where` is a raw dict from JSON input. Use `parse_where_clause()`
    to convert to typed `WhereClause` before passing to `SearchParams`.
    """

    query: str | None = None
    where: WhereClauseDict | None = None
    sort: list[SortClause] | None = None
    limit: Annotated[int, Meta(ge=1, le=100)] | None = 50


class SearchParams(Struct):
    """Internal search parameters with parsed WhereClause.

    Use this for passing to the search service after parsing the raw
    SearchQuerySchema input.
    """

    query: str | None = None
    where: "WhereClause | None" = None
    sort: list[SortClause] | None = None
    limit: int | None = 50


class IndexResponse(Struct):
    id: str


class SearchResultDocument(Struct):
    id: str
    title: str
    content: str
    size: int
    depth: int
    path: str
    numchild: int
    created_at: str
    updated_at: str
    reach: str | None = None
    tags: list[str] = []
    number_of_users: list[int] | None = None
    number_of_groups: list[int] | None = None


class SearchResponse(Struct):
    data: list[SearchResultDocument]
    total: int
    limit: int


# All allowed field names for validation
_ALLOWED_FIELDS: frozenset[str] = frozenset(
    [
        # UserQueryField
        "id", "title", "content", "depth", "path", "numchild",
        "created_at", "updated_at", "size", "reach", "tags",
        # SystemQueryField
        "is_active", "users", "groups", "service",
    ]
)


def _parse_where_clause_inner(data: dict) -> "AndClause | OrClause | NotClause | FieldCondition":
    if "and" in data:
        return AndClause(and_=[_parse_where_clause_inner(c) for c in data["and"]])
    elif "or" in data:
        return OrClause(or_=[_parse_where_clause_inner(c) for c in data["or"]])
    elif "not" in data:
        return NotClause(not_=_parse_where_clause_inner(data["not"]))
    elif "field" in data and "op" in data and "value" in data:
        field_name = data["field"]
        if not isinstance(field_name, str):
            raise msgspec.ValidationError(f"Field must be a string, got {type(field_name).__name__}")
        if field_name not in _ALLOWED_FIELDS:
            raise msgspec.ValidationError(f"Unknown field: {field_name!r}")
        try:
            op = Operator(data["op"])
        except ValueError as e:
            raise msgspec.ValidationError(str(e)) from None
        return FieldCondition(
            field=field_name,
            op=op,
            value=data["value"],
        )
    else:
        raise msgspec.ValidationError(f"Invalid where clause: {data}")


def parse_where_clause(
    data: dict | None,
) -> "AndClause | OrClause | NotClause | FieldCondition | None":
    """Parse a where clause dict into the appropriate struct type."""
    if data is None:
        return None
    return _parse_where_clause_inner(data)
