"""Pydantic model to validate documents before indexation."""

from typing import Annotated, List, Literal, Optional

from django.utils import timezone
from django.utils.text import slugify

from pydantic import (
    UUID4,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    conint,
    field_validator,
    model_validator,
)

from . import enums


class DocumentSchema(BaseModel):
    """Schema for validating the documents submitted to our API for indexing"""

    id: UUID4
    title: Annotated[str, Field(max_length=300, min_length=0)]
    depth: Annotated[int, Field(ge=0)]
    path: Annotated[str, Field(max_length=300)]
    numchild: Annotated[int, Field(ge=0)]
    content: Annotated[str, Field(min_length=0)]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    size: Annotated[int, Field(ge=0, le=100 * 1024**3)]  # File size limited to 100GB
    users: List[Annotated[str, Field(max_length=50)]] = Field(default_factory=list)
    groups: List[Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]] = Field(
        default_factory=list
    )
    reach: Optional[enums.ReachEnum] = Field(default=enums.ReachEnum.RESTRICTED)
    tags: List[Annotated[str, Field(max_length=100)]] = Field(default_factory=list)
    is_active: bool

    model_config = ConfigDict(
        str_min_length=1, str_strip_whitespace=True, use_enum_values=True
    )

    @field_validator("title")
    @staticmethod
    def normalize_title(value):
        """Normalize the title field by stripping whitespace and converting to lowercase"""
        return value.strip().lower()

    @field_validator("created_at", "updated_at")
    @staticmethod
    def must_be_past(value, info):
        """Validate that `created_at` and `updated_at` fields are in the past"""
        if value >= timezone.now():
            raise ValueError(f"{info.field_name} must be earlier than now")
        return value

    @model_validator(mode="after")
    def check_empty_content(self):
        """Validate that either `title` or `content` are not empty."""
        if not self.title and not self.content:
            raise ValueError("Either title or content should have at least 1 character")
        return self

    @model_validator(mode="after")
    def check_update_at_after_created_at(self):
        """Date and time of last modification should be later than date and time of creation"""
        if self.created_at > self.updated_at:
            raise ValueError("updated_at must be later than created_at")
        return self

    @field_validator("groups")
    @staticmethod
    def validate_groups(groups):
        """Validate that group slugs are properly formatted as lowercase and hyphen-separated"""
        validated_groups = []
        for value in groups:
            slug = slugify(value)
            if value != slug:
                raise ValueError(
                    f"Groups must be slugs (lowercase, hyphen-separated): {slug:s}"
                )
            validated_groups.append(value)
        return validated_groups


def cleanlist(value):
    """Build a list of strings from a string, None (empty list) or a list of objects."""
    if isinstance(value, str):
        # Convert comma-separated strings to list
        return [s.strip() for s in value.split(",") if s.strip()]

    if isinstance(value, list):
        # Clean up list of strings
        return [str(s).strip() for s in value if s is not None and str(s).strip()]

    if value is None:
        return []

    raise ValueError()


StringListParameter = Annotated[List[str], BeforeValidator(cleanlist)]


class SearchQueryParametersSchema(BaseModel):
    """Schema for validating the querystring on the search API endpoint"""

    q: str
    services: StringListParameter = Field(default_factory=list)
    visited: StringListParameter = Field(default_factory=list)
    reach: Optional[enums.ReachEnum] = None
    tags: StringListParameter = Field(default_factory=list)
    path: Optional[str] = None
    order_by: Optional[Literal[enums.ORDER_BY_OPTIONS]] = Field(default=enums.RELEVANCE)
    order_direction: Optional[Literal["asc", "desc"]] = Field(default="desc")
    nb_results: Optional[conint(ge=1, le=300)] = Field(default=50)
    rerank: Optional[bool] = Field(default=None)


class DeleteDocumentsSchema(BaseModel):
    """Schema for validating the delete documents request"""

    service: str = Field(max_length=300)
    document_ids: Optional[List[str]] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)

    @model_validator(mode="after")
    def check_at_least_one_filter(self):
        """Ensure at least one of document_ids or tags is provided"""
        if not self.document_ids and not self.tags:
            raise ValueError(
                "At least one of 'document_ids' or 'tags' must be provided"
            )
        return self
