"""Enums for find's core app."""

from enum import Enum

# Reach


class ReachEnum(str, Enum):
    """Publication options for indexed documents"""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    RESTRICTED = "restricted"


# Search type


class SearchTypeEnum(str, Enum):
    """Search type options"""

    HYBRID = "hybrid"
    FULL_TEXT = "full-text"


class IndexingStatusEnum(str, Enum):
    """Indexing status options for documents"""

    TO_BE_EMBEDDED = "to-be-embedded"
    READY = "ready"


# Fields

CREATED_AT = "created_at"
DEPTH = "depth"
PATH = "path"
NUMCHILD = "numchild"
REACH = "reach"
SIZE = "size"
TAGS = "tags"
TITLE = "title"
CONTENT = "content"
UPDATED_AT = "updated_at"
USERS = "users"
GROUPS = "groups"

RELEVANCE = "relevance"

ORDER_BY_OPTIONS = (RELEVANCE, TITLE, CREATED_AT, UPDATED_AT, SIZE, REACH)
SOURCE_FIELDS = (
    TITLE,
    CONTENT,
    SIZE,
    DEPTH,
    PATH,
    NUMCHILD,
    CREATED_AT,
    UPDATED_AT,
    REACH,
    TAGS,
)
