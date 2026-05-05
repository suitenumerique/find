"""Pydantic models for service configuration from environment variables"""

from django.conf import settings as django_settings
from django.utils.text import slugify

from pydantic import BaseModel, StringConstraints, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Annotated

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class ServiceConfig(BaseModel):
    """Configuration for a single service"""

    token: NonEmptyStr
    client_id: NonEmptyStr
    name: str = ""

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


class ServicesSettings(BaseSettings):
    """Settings for all services loaded from environment variables"""

    services: dict[str, ServiceConfig] = {}

    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
    )

    def get_service_by_token(self, token: str) -> ServiceConfig | None:
        """Get a service configuration by its token

        Args:
            token: The service token to search for

        Returns:
            ServiceConfig with name set if found, None otherwise
        """
        for service_name, config in self.services.items():
            if config.token == token:
                config.name = service_name
                return config
        return None

    def get_service_by_client_id(self, client_id: str) -> ServiceConfig | None:
        """Get a service configuration by its client_id

        Args:
            client_id: The client_id to search for

        Returns:
            ServiceConfig with name set if found, None otherwise
        """
        for service_name, config in self.services.items():
            if config.client_id == client_id:
                config.name = service_name
                return config
        return None


__all__ = ["ServiceConfig", "ServicesSettings"]
