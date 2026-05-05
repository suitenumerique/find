"""Service configuration models."""

import logging

from django.conf import settings as django_settings
from django.utils.text import slugify

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
)
from typing_extensions import Annotated

logger = logging.getLogger(__name__)

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class ServiceConfig(BaseModel):
    """Configuration for a single service."""

    name: NonEmptyStr
    token: NonEmptyStr
    client_id: NonEmptyStr

    @field_validator("name", mode="before")
    @classmethod
    def slugify_name(cls, v: str) -> str:
        """Normalize service name to valid OpenSearch index format."""
        return slugify(v) if v else v

    @computed_field
    @property
    def index_name(self) -> str:
        """OpenSearch index name derived from service name."""
        return f"{django_settings.OPENSEARCH_INDEX_PREFIX}-{self.name}"


class ServicesConfig(BaseModel):
    """Container for all service configurations."""

    services: list[ServiceConfig] = Field(default_factory=list, alias="service")

    def get_by_token(self, token: str) -> ServiceConfig | None:
        """Look up a service by its authentication token."""
        for service in self.services:
            if service.token == token:
                return service
        return None

    def get_by_client_id(self, client_id: str) -> ServiceConfig | None:
        """Look up a service by its OIDC client ID."""
        for service in self.services:
            if service.client_id == client_id:
                return service
        return None


__all__ = ["ServiceConfig", "ServicesConfig"]
