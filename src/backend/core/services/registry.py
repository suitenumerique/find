"""Service registry using pydantic-settings for environment-based configuration."""

import re
from functools import cache
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# NonEmptyStr type - string with minimum length 1
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]

# Service name pattern: lowercase alphanumeric + underscore only
SERVICE_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")


class Service(BaseModel):
    """A service that can authenticate to the API."""

    model_config = ConfigDict(extra="ignore")

    client_id: NonEmptyStr
    token: NonEmptyStr


class ServiceRegistry(BaseSettings):
    """Service registry parsed from environment variables.

    Environment variable format:
        SERVICES__<NAME>__TOKEN=xxx
        SERVICES__<NAME>__CLIENT_ID=yyy

    Example:
        SERVICES__DOCS__TOKEN=secret123
        SERVICES__DOCS__CLIENT_ID=impress
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        case_sensitive=False,
        env_ignore_empty=False,
    )

    services: dict[str, Service] = {}

    @field_validator("services", mode="after")
    @classmethod
    def normalize_and_validate(cls, services: dict[str, Service]) -> dict[str, Service]:
        """Normalize service names to lowercase and validate uniqueness."""
        normalized: dict[str, Service] = {}
        seen_tokens: dict[str, str] = {}  # token -> service_name

        for name, service in services.items():
            # Normalize name to lowercase
            lower_name = name.lower()

            # Validate service name pattern
            if not SERVICE_NAME_PATTERN.match(lower_name):
                raise ValueError(
                    f"Invalid service name '{name}': must match pattern ^[a-z0-9_]+$ "
                    "(lowercase alphanumeric and underscore only)"
                )

            # Check for duplicate tokens
            if service.token in seen_tokens:
                raise ValueError(
                    f"Duplicate token: services '{seen_tokens[service.token]}' and "
                    f"'{lower_name}' have the same token"
                )
            seen_tokens[service.token] = lower_name

            normalized[lower_name] = service

        return normalized

    def get_by_token(self, token: str) -> tuple[str, Service] | None:
        """Look up a service by its token.

        Returns:
            Tuple of (service_name, Service) if found, None otherwise.
        """
        for name, service in self.services.items():
            if service.token == token:
                return (name, service)
        return None

    def get_by_name(self, name: str) -> Service | None:
        """Look up a service by its name.

        Returns:
            Service instance if found, None otherwise.
        """
        return self.services.get(name.lower())


@cache
def get_registry() -> ServiceRegistry:
    """Get the service registry singleton (cached on first call)."""
    return ServiceRegistry()


def get_service_by_token(token: str) -> tuple[str, Service] | None:
    """Look up a service by its token.

    Convenience function that delegates to the registry singleton.

    Returns:
        Tuple of (service_name, Service) if found, None otherwise.
    """
    return get_registry().get_by_token(token)


def get_service_by_name(name: str) -> Service | None:
    """Look up a service by its name.

    Convenience function that delegates to the registry singleton.

    Returns:
        Service instance if found, None otherwise.
    """
    return get_registry().get_by_name(name)
