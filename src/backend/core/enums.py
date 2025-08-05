"""Enums for find's core app."""

from enum import Enum

# Reach


class ReachEnum(str, Enum):
    """Publication options for indexed documents"""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    RESTRICTED = "restricted"


# Fields

CREATED_AT = "created_at"
REACH = "reach"
SIZE = "size"
TITLE = "title"
UPDATED_AT = "updated_at"

RELEVANCE = "relevance"

ORDER_BY_OPTIONS = (RELEVANCE, TITLE, CREATED_AT, UPDATED_AT, SIZE, REACH)
SOURCE_FIELDS = (TITLE, SIZE, CREATED_AT, UPDATED_AT, REACH)
