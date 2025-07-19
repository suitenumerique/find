"""Pydantic model to validate documents before indexation."""

from typing import Annotated, List, Literal, Optional

from django.utils import timezone
from django.utils.text import slugify

from pydantic import (
    UUID4,
    AwareDatetime,
    BaseModel,
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
    title: Annotated[str, Field(max_length=300)]
    content: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    size: Annotated[int, Field(ge=0, le=100 * 1024**3)]  # File size limited to 100GB
    users: List[UUID4] = Field(default_factory=list)
    groups: List[Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]] = Field(
        default_factory=list
    )
    reach: Optional[enums.Reach] = Field(default=enums.Reach.RESTRICTED)

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


class SearchQueryParametersSchema(BaseModel):
    """Schema for validating the querystring on the search API endpoint"""

    q: str
    reach: Optional[enums.Reach] = None
    order_by: Optional[Literal[enums.ORDER_BY_OPTIONS]] = Field(default=enums.RELEVANCE)
    order_direction: Optional[Literal["asc", "desc"]] = Field(default="desc")
    page_number: Optional[conint(ge=1)] = Field(default=1)
    page_size: Optional[conint(ge=1, le=100)] = Field(default=50)

    @model_validator(mode="before")
    @staticmethod
    def handle_lists(values):
        """Make sure we get strings and ignore multiple values."""
        for key, value in values.items():
            if isinstance(value, list):
                # Take the first item if it's a list
                values[key] = value[0] if value else None
        return values
